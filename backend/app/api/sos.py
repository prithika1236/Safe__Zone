"""SafeZone Emergency SOS API.

Provides endpoints for:
- Citizen triggering emergency SOS distress calls with coordinate validation & automatic dispatch
- Citizen retrieving active SOS status & response timeline with strict privacy enforcement
- Viewing active and pending SOS emergency alerts (Police & Admin)
- Police responding to distress calls (ASSIGNED -> ACCEPTED -> EN_ROUTE -> ARRIVED -> RESOLVED)
- Police decline and loop-free redispatch to next eligible patrol
- Admin manual dispatch override.
"""

from datetime import datetime
import math
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, and_
from sqlalchemy.orm import joinedload

from app.database.session import get_async_db
from app.core.security import require_police, require_admin, get_current_user, decode_access_token
from app.models.user import User, UserRole
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.sos import SOSRequest
from app.services.dispatch_service import dispatch_service
from app.services.location_service import LocationService
from app.services.live_manager import live_sos_manager

router = APIRouter(prefix="/sos", tags=["SOS Emergency"])



# ==========================================
# SCHEMAS
# ==========================================

class SOSTriggerRequest(BaseModel):
    latitude: float = Field(..., description="GPS Latitude (-90.0 to 90.0)")
    longitude: float = Field(..., description="GPS Longitude (-180.0 to 180.0)")
    notes: Optional[str] = None

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if v < -90.0 or v > 90.0:
            raise ValueError("Latitude must be between -90.0 and 90.0 degrees.")
        if v == 0.0:
            raise ValueError("Invalid GPS latitude coordinate (0.0). Valid GPS fix required.")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if v < -180.0 or v > 180.0:
            raise ValueError("Longitude must be between -180.0 and 180.0 degrees.")
        if v == 0.0:
            raise ValueError("Invalid GPS longitude coordinate (0.0). Valid GPS fix required.")
        return v


class CitizenSOSStatusResponse(BaseModel):
    id: int
    status: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    approximate_distance_km: Optional[float] = None
    estimated_arrival_minutes: Optional[int] = None
    notes: Optional[str] = None


class SOSResponse(BaseModel):
    id: int
    citizen_id: int
    latitude: float
    longitude: float
    status: str
    assigned_patrol_id: Optional[int] = None
    assigned_officer_id: Optional[int] = None
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SOSStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="ACCEPTED, EN_ROUTE, ARRIVED, RESOLVED, CANCELLED")
    notes: Optional[str] = None


class SOSManualDispatchRequest(BaseModel):
    patrol_unit_id: int
    officer_id: Optional[int] = None


class PoliceTodaySummaryResponse(BaseModel):
    handled_today: int
    resolved_today: int
    recent: List[SOSResponse]


@router.get("/status")
def sos_status():
    return {"module": "sos", "status": "ready"}


# ==========================================
# CITIZEN SOS ENDPOINTS
# ==========================================

@router.post(
    "/trigger",
    response_model=CitizenSOSStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Citizen Triggers Emergency SOS Distress Alert",
)
async def trigger_sos(
    payload: SOSTriggerRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Citizen creates an urgent panic alert with verified GPS coordinates and triggers automated dispatch."""
    sos = await dispatch_service.create_and_dispatch_sos(
        db=db,
        citizen=current_user,
        latitude=payload.latitude,
        longitude=payload.longitude,
        notes=payload.notes,
    )

    approx_dist: Optional[float] = None
    if sos.assigned_patrol and sos.assigned_patrol.current_latitude and sos.assigned_patrol.current_longitude:
        approx_dist = round(
            LocationService.haversine_distance(
                sos.latitude,
                sos.longitude,
                sos.assigned_patrol.current_latitude,
                sos.assigned_patrol.current_longitude,
            ),
            2,
        )

    return CitizenSOSStatusResponse(
        id=sos.id,
        status=sos.status,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        approximate_distance_km=approx_dist,
        estimated_arrival_minutes=None,  # Null when road routing is unavailable
        notes=sos.notes,
    )


@router.get(
    "/my-active",
    response_model=Optional[CitizenSOSStatusResponse],
    summary="Citizen Gets Current Active SOS Response Status",
)
async def get_my_active_sos(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the logged-in citizen's active SOS alert with strict privacy enforcement."""
    stmt = (
        select(SOSRequest)
        .options(
            joinedload(SOSRequest.assigned_patrol),
            joinedload(SOSRequest.assigned_officer),
        )
        .where(
            and_(
                SOSRequest.citizen_id == current_user.id,
                SOSRequest.status.in_(["PENDING", "SUBMITTED", "ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED", "NO_AVAILABLE_PATROL"]),
            )
        )
        .order_by(desc(SOSRequest.id))
    )
    res = await db.execute(stmt)
    sos = res.scalar_one_or_none()
    if not sos:
        return None

    approx_dist: Optional[float] = None
    if sos.assigned_patrol and sos.assigned_patrol.current_latitude and sos.assigned_patrol.current_longitude:
        approx_dist = round(
            LocationService.haversine_distance(
                sos.latitude,
                sos.longitude,
                sos.assigned_patrol.current_latitude,
                sos.assigned_patrol.current_longitude,
            ),
            2,
        )

    return CitizenSOSStatusResponse(
        id=sos.id,
        status=sos.status,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        approximate_distance_km=approx_dist,
        estimated_arrival_minutes=None,  # Null when road routing is unavailable
        notes=sos.notes,
    )


@router.get(
    "/my-history",
    response_model=List[CitizenSOSStatusResponse],
    summary="Citizen Gets Historical SOS Distress Calls",
)
async def get_my_sos_history(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the logged-in citizen's entire SOS distress history, newest first, with privacy guarantees."""
    stmt = (
        select(SOSRequest)
        .options(
            joinedload(SOSRequest.assigned_patrol),
            joinedload(SOSRequest.assigned_officer),
        )
        .where(SOSRequest.citizen_id == current_user.id)
        .order_by(desc(SOSRequest.triggered_at), desc(SOSRequest.id))
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    results = []
    for sos in records:
        approx_dist: Optional[float] = None
        if sos.assigned_patrol and sos.assigned_patrol.current_latitude and sos.assigned_patrol.current_longitude:
            approx_dist = round(
                LocationService.haversine_distance(
                    sos.latitude,
                    sos.longitude,
                    sos.assigned_patrol.current_latitude,
                    sos.assigned_patrol.current_longitude,
                ),
                2,
            )
        results.append(
            CitizenSOSStatusResponse(
                id=sos.id,
                status=sos.status,
                triggered_at=sos.triggered_at,
                resolved_at=sos.resolved_at,
                approximate_distance_km=approx_dist,
                estimated_arrival_minutes=None,
                notes=sos.notes,
            )
        )
    return results


# ==========================================
# POLICE & ADMIN SOS MANAGEMENT ENDPOINTS
# ==========================================

@router.get(
    "/active",
    response_model=List[SOSResponse],
    summary="List Active and Dispatched SOS Alerts (Police & Admin)",
)
async def list_active_sos(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List pending/active emergency SOS distress alerts."""
    if current_user.role not in [UserRole.POLICE, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Only Police and Admin may monitor SOS alerts.",
        )

    stmt = (
        select(SOSRequest)
        .where(SOSRequest.status.in_(["PENDING", "SUBMITTED", "ACTIVE", "ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED", "NO_AVAILABLE_PATROL"]))
        .order_by(desc(SOSRequest.triggered_at))
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        SOSResponse(
            id=r.id,
            citizen_id=r.citizen_id,
            latitude=r.latitude,
            longitude=r.longitude,
            status=r.status,
            assigned_patrol_id=r.assigned_patrol_id,
            assigned_officer_id=r.assigned_officer_id,
            triggered_at=r.triggered_at,
            resolved_at=r.resolved_at,
            notes=r.notes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@router.get(
    "/police/history",
    response_model=List[SOSResponse],
    summary="Police Officer Views Emergency Response History",
)
async def get_police_sos_history(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Retrieve emergency incidents assigned to or handled by the authenticated officer, newest first."""
    off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
    off_res = await db.execute(off_stmt)
    officer = off_res.scalar_one_or_none()
    if not officer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Police officer profile not found for the authenticated user.",
        )

    stmt = (
        select(SOSRequest)
        .where(SOSRequest.assigned_officer_id == officer.id)
        .order_by(desc(SOSRequest.triggered_at), desc(SOSRequest.id))
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        SOSResponse(
            id=r.id,
            citizen_id=r.citizen_id,
            latitude=r.latitude,
            longitude=r.longitude,
            status=r.status,
            assigned_patrol_id=r.assigned_patrol_id,
            assigned_officer_id=r.assigned_officer_id,
            triggered_at=r.triggered_at,
            resolved_at=r.resolved_at,
            notes=r.notes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@router.get(
    "/police/today-summary",
    response_model=PoliceTodaySummaryResponse,
    summary="Police Officer Gets Today's Emergency Response Summary",
)
async def get_police_today_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Calculate today's metrics for the logged-in officer only."""
    off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
    off_res = await db.execute(off_stmt)
    officer = off_res.scalar_one_or_none()
    if not officer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Police officer profile not found for the authenticated user.",
        )

    # Start of today (UTC)
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)

    # Query all incidents assigned to this officer
    stmt = (
        select(SOSRequest)
        .where(SOSRequest.assigned_officer_id == officer.id)
        .order_by(desc(SOSRequest.triggered_at), desc(SOSRequest.id))
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    today_records = [r for r in records if r.triggered_at >= today_start or (r.resolved_at and r.resolved_at >= today_start)]
    handled_today = len(today_records)
    resolved_today = len([r for r in today_records if r.status == "RESOLVED"])

    recent_responses = [
        SOSResponse(
            id=r.id,
            citizen_id=r.citizen_id,
            latitude=r.latitude,
            longitude=r.longitude,
            status=r.status,
            assigned_patrol_id=r.assigned_patrol_id,
            assigned_officer_id=r.assigned_officer_id,
            triggered_at=r.triggered_at,
            resolved_at=r.resolved_at,
            notes=r.notes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in today_records[:10]
    ]

    return PoliceTodaySummaryResponse(
        handled_today=handled_today,
        resolved_today=resolved_today,
        recent=recent_responses,
    )


@router.get(
    "/admin/history",
    response_model=List[SOSResponse],
    summary="Admin Views Complete Emergency Response History (Admin Only)",
)
async def get_admin_sos_history(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
    status_filter: Optional[str] = Query(None, alias="status", description="Optional status filter"),
):
    """Retrieve all historical and active emergency SOS distress incidents for administrative review, newest first."""
    stmt = select(SOSRequest).order_by(desc(SOSRequest.triggered_at), desc(SOSRequest.id))
    if status_filter:
        stmt = stmt.where(SOSRequest.status == status_filter.upper())

    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        SOSResponse(
            id=r.id,
            citizen_id=r.citizen_id,
            latitude=r.latitude,
            longitude=r.longitude,
            status=r.status,
            assigned_patrol_id=r.assigned_patrol_id,
            assigned_officer_id=r.assigned_officer_id,
            triggered_at=r.triggered_at,
            resolved_at=r.resolved_at,
            notes=r.notes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@router.get(
    "/{sos_id}",
    summary="Get SOS Alert Details by ID (Strict Role-Based Access Control)",
)
async def get_sos_by_id(
    sos_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve specific SOS incident with strict role-based data protection:
    - CITIZEN: Only their own SOS alert, formatted with privacy guarantees (CitizenSOSStatusResponse).
    - POLICE: Only incidents assigned to / handled by that officer (SOSResponse).
    - ADMIN: Administrative access to any SOS incident (SOSResponse).
    """
    stmt = (
        select(SOSRequest)
        .options(
            joinedload(SOSRequest.assigned_patrol),
            joinedload(SOSRequest.assigned_officer),
        )
        .where(SOSRequest.id == sos_id)
    )
    res = await db.execute(stmt)
    sos = res.scalar_one_or_none()
    if not sos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SOS emergency alert #{sos_id} not found.",
        )

    # Strict authorization checks
    if current_user.role == UserRole.CITIZEN:
        if sos.citizen_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You may only view your own emergency SOS alerts.",
            )

        approx_dist: Optional[float] = None
        if sos.assigned_patrol and sos.assigned_patrol.current_latitude and sos.assigned_patrol.current_longitude:
            approx_dist = round(
                LocationService.haversine_distance(
                    sos.latitude,
                    sos.longitude,
                    sos.assigned_patrol.current_latitude,
                    sos.assigned_patrol.current_longitude,
                ),
                2,
            )

        return CitizenSOSStatusResponse(
            id=sos.id,
            status=sos.status,
            triggered_at=sos.triggered_at,
            resolved_at=sos.resolved_at,
            approximate_distance_km=approx_dist,
            estimated_arrival_minutes=None,
            notes=sos.notes,
        )

    elif current_user.role == UserRole.POLICE:
        off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
        off_res = await db.execute(off_stmt)
        officer = off_res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Officer profile not found for authenticated user.",
            )

        # Police officer can only access if they are assigned to this SOS
        if sos.assigned_officer_id != officer.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You may only access emergency SOS dispatches assigned to you.",
            )

        return SOSResponse(
            id=sos.id,
            citizen_id=sos.citizen_id,
            latitude=sos.latitude,
            longitude=sos.longitude,
            status=sos.status,
            assigned_patrol_id=sos.assigned_patrol_id,
            assigned_officer_id=sos.assigned_officer_id,
            triggered_at=sos.triggered_at,
            resolved_at=sos.resolved_at,
            notes=sos.notes,
            created_at=sos.created_at,
            updated_at=sos.updated_at,
        )

    elif current_user.role == UserRole.ADMIN:
        return SOSResponse(
            id=sos.id,
            citizen_id=sos.citizen_id,
            latitude=sos.latitude,
            longitude=sos.longitude,
            status=sos.status,
            assigned_patrol_id=sos.assigned_patrol_id,
            assigned_officer_id=sos.assigned_officer_id,
            triggered_at=sos.triggered_at,
            resolved_at=sos.resolved_at,
            notes=sos.notes,
            created_at=sos.created_at,
            updated_at=sos.updated_at,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden.",
        )


@router.post(
    "/{sos_id}/accept",
    response_model=SOSResponse,
    summary="Police Officer Accepts SOS Dispatch (Police Only)",
)
async def accept_sos(
    sos_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Officer accepts SOS emergency call and transitions status: ASSIGNED -> ACCEPTED."""
    sos = await dispatch_service.accept_dispatch(db=db, sos_id=sos_id, current_user=current_user)

    return SOSResponse(
        id=sos.id,
        citizen_id=sos.citizen_id,
        latitude=sos.latitude,
        longitude=sos.longitude,
        status=sos.status,
        assigned_patrol_id=sos.assigned_patrol_id,
        assigned_officer_id=sos.assigned_officer_id,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        notes=sos.notes,
        created_at=sos.created_at,
        updated_at=sos.updated_at,
    )


@router.post(
    "/{sos_id}/status",
    response_model=SOSResponse,
    summary="Update SOS Lifecycle Status (Police or Admin)",
)
async def update_sos_status(
    sos_id: int,
    request: SOSStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Progress SOS status through validated state machine: ACCEPTED -> EN_ROUTE -> ARRIVED -> RESOLVED."""
    if current_user.role not in [UserRole.POLICE, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Only Police and Admin may update SOS status.",
        )

    sos = await dispatch_service.update_dispatch_status(
        db=db,
        sos_id=sos_id,
        target_status=request.status,
        current_user=current_user,
        notes=request.notes,
    )

    return SOSResponse(
        id=sos.id,
        citizen_id=sos.citizen_id,
        latitude=sos.latitude,
        longitude=sos.longitude,
        status=sos.status,
        assigned_patrol_id=sos.assigned_patrol_id,
        assigned_officer_id=sos.assigned_officer_id,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        notes=sos.notes,
        created_at=sos.created_at,
        updated_at=sos.updated_at,
    )


@router.post(
    "/{sos_id}/decline",
    response_model=SOSResponse,
    summary="Police Officer Declines SOS Response (Police Only)",
)
async def decline_sos(
    sos_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Decline SOS dispatch and trigger redispatch to the next nearest eligible patrol."""
    sos = await dispatch_service.decline_and_redispatch(db=db, sos_id=sos_id, current_user=current_user)

    return SOSResponse(
        id=sos.id,
        citizen_id=sos.citizen_id,
        latitude=sos.latitude,
        longitude=sos.longitude,
        status=sos.status,
        assigned_patrol_id=sos.assigned_patrol_id,
        assigned_officer_id=sos.assigned_officer_id,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        notes=sos.notes,
        created_at=sos.created_at,
        updated_at=sos.updated_at,
    )


@router.post(
    "/{sos_id}/dispatch",
    response_model=SOSResponse,
    summary="Admin Manual Patrol Assignment / Override (Admin Only)",
)
async def manual_admin_dispatch(
    sos_id: int,
    payload: SOSManualDispatchRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin manually assigns or overrides patrol unit dispatch for an emergency."""
    sos = await dispatch_service.manual_admin_dispatch(
        db=db,
        sos_id=sos_id,
        patrol_unit_id=payload.patrol_unit_id,
        officer_id=payload.officer_id,
    )

    return SOSResponse(
        id=sos.id,
        citizen_id=sos.citizen_id,
        latitude=sos.latitude,
        longitude=sos.longitude,
        status=sos.status,
        assigned_patrol_id=sos.assigned_patrol_id,
        assigned_officer_id=sos.assigned_officer_id,
        triggered_at=sos.triggered_at,
        resolved_at=sos.resolved_at,
        notes=sos.notes,
        created_at=sos.created_at,
        updated_at=sos.updated_at,
    )


# ==========================================
# WEBSOCKET LIVE STREAMING
# ==========================================

@router.websocket("/ws/{sos_id}")
async def sos_websocket_endpoint(
    websocket: WebSocket,
    sos_id: int,
    token: Optional[str] = Query(None),
):
    """Real-time WebSocket connection for active SOS status and response telemetry."""
    role = "citizen"
    user_id = None
    if token:
        try:
            token_payload = decode_access_token(token)
            role = token_payload.role.lower() if token_payload.role else "citizen"
            user_id = int(token_payload.sub)
        except Exception:
            role = "citizen"
            user_id = None

    await live_sos_manager.connect(websocket, sos_id, role=role, user_id=user_id)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        live_sos_manager.disconnect(websocket, sos_id)
    except Exception:
        live_sos_manager.disconnect(websocket, sos_id)

