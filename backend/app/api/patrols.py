"""SafeZone Patrol Dispatch and Assignment API.

Provides endpoints for:
- Manual and Automated Patrol Unit Assignment to approved PRPs (Admin Only)
- Officer viewing active deployment assignment (Police)
- Consistent Assignment Lifecycle Management:
    ASSIGNED -> ACKNOWLEDGED -> AT_PRP -> COMPLETED (or UNAVAILABLE / CANCELLED)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.core.security import require_admin, require_police, get_current_user
from app.models.user import User, UserRole
from app.services.patrol_service import patrol_service
from app.schemas.patrol import (
    ManualAssignmentRequest,
    AutoAssignmentRequest,
    AssignmentStatusUpdateRequest,
    PatrolAssignmentResponse,
    AutoAssignmentResponse,
    DutyStatusUpdateRequest,
    LocationUpdateRequest,
    PoliceOfficerResponse,
)

router = APIRouter(prefix="/patrols", tags=["Patrols & Assignments"])


@router.get("/status")
def patrols_status():
    return {"module": "patrols", "status": "ready"}


@router.get("/secure-check")
def police_secure_check(current_user: User = Depends(require_police)):
    return {
        "message": "Police authorization verified",
        "officer_email": current_user.email,
        "role": current_user.role,
    }


# ==========================================
# PATROL ASSIGNMENTS (ADMIN ONLY)
# ==========================================

@router.post(
    "/assignments/manual",
    response_model=PatrolAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manual Patrol Unit Assignment to PRP (Admin Only)",
)
async def create_manual_assignment(
    request: ManualAssignmentRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Manually assign an available police officer and patrol unit to an approved PRP.
    
    Prevents duplicate incompatible assignments.
    """
    return await patrol_service.create_manual_assignment(db=db, req=request)


@router.post(
    "/assignments/auto",
    response_model=AutoAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Automated Patrol Assignment Optimization (Admin Only)",
)
async def create_auto_assignment(
    request: AutoAssignmentRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Run Google OR-Tools bipartite matching to optimally assign resources to unassigned PRPs."""
    return await patrol_service.run_auto_assignment(db=db, req=request)


# ==========================================
# ASSIGNMENT INSPECTION & LIFECYCLE
# ==========================================

@router.get(
    "/assignments",
    response_model=List[PatrolAssignmentResponse],
    summary="List Patrol Assignments (Police & Admin)",
)
async def list_assignments(
    status_filter: Optional[str] = Query(None, alias="status", description="ASSIGNED, ACKNOWLEDGED, AT_PRP, COMPLETED, CANCELLED"),
    officer_id: Optional[int] = Query(None, description="Filter by officer ID"),
    patrol_unit_id: Optional[int] = Query(None, description="Filter by unit ID"),
    prp_id: Optional[int] = Query(None, description="Filter by PRP ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """List patrol assignments with status and entity filters."""
    return await patrol_service.list_assignments(
        db=db,
        status_filter=status_filter,
        officer_id=officer_id,
        patrol_unit_id=patrol_unit_id,
        prp_id=prp_id,
    )


@router.get(
    "/my-assignment",
    response_model=PatrolAssignmentResponse,
    summary="Get My Active Patrol Assignment (Police Only)",
)
async def get_my_active_assignment(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Retrieve the current active patrol assignment for the logged-in officer."""
    assignment = await patrol_service.get_my_active_assignment(db=db, officer_user_id=current_user.id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active patrol assignment found for the current officer.",
        )
    return assignment


@router.post(
    "/assignments/{assignment_id}/status",
    response_model=PatrolAssignmentResponse,
    summary="Update Assignment Status (Police or Admin)",
)
async def update_assignment_status(
    assignment_id: int,
    request: AssignmentStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Transition assignment state: ASSIGNED -> ACKNOWLEDGED -> AT_PRP -> COMPLETED."""
    if current_user.role not in [UserRole.POLICE, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Only Police or Admin can update assignment status.",
        )
    return await patrol_service.update_assignment_status(
        db=db, assignment_id=assignment_id, new_status=request.status, current_user=current_user
    )


@router.post(
    "/assignments/{assignment_id}/acknowledge",
    response_model=PatrolAssignmentResponse,
    summary="Acknowledge Patrol Assignment (Police)",
)
async def acknowledge_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Officer acknowledges receipt of patrol deployment instructions."""
    return await patrol_service.update_assignment_status(
        db=db, assignment_id=assignment_id, new_status="ACKNOWLEDGED", current_user=current_user
    )


@router.post(
    "/assignments/{assignment_id}/at-prp",
    response_model=PatrolAssignmentResponse,
    summary="Mark Unit Arrived at PRP (Police)",
)
async def mark_at_prp(
    assignment_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Officer marks unit arrival at the designated Patrol Response Point."""
    return await patrol_service.update_assignment_status(
        db=db, assignment_id=assignment_id, new_status="AT_PRP", current_user=current_user
    )


@router.post(
    "/assignments/{assignment_id}/complete",
    response_model=PatrolAssignmentResponse,
    summary="Complete Patrol Assignment (Police or Admin)",
)
async def complete_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Complete patrol assignment and release unit and officer back to available pool."""
    return await patrol_service.update_assignment_status(
        db=db, assignment_id=assignment_id, new_status="COMPLETED", current_user=current_user
    )


# ==========================================
# POLICE MOBILE OPERATIONAL ENDPOINTS
# ==========================================

@router.get(
    "/my-profile",
    response_model=PoliceOfficerResponse,
    summary="Get My Police Officer Profile (Police Only)",
)
async def get_my_profile(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Retrieve police officer profile, badge, rank, station and current duty status."""
    return await patrol_service.get_officer_by_user_id(db=db, user_id=current_user.id)


@router.post(
    "/duty-status",
    response_model=PoliceOfficerResponse,
    summary="Update Police Duty Status (Police Only)",
)
async def update_my_duty_status(
    request: DutyStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Toggle officer on-duty and availability status."""
    return await patrol_service.update_duty_status(
        db=db,
        user_id=current_user.id,
        on_duty=request.on_duty,
        is_available=request.is_available,
    )


@router.post(
    "/location",
    summary="Send Controlled Location Telemetry (Police Only)",
)
async def update_my_location(
    request: LocationUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Record current GPS coordinates for active-duty tracking."""
    return await patrol_service.record_officer_location(
        db=db,
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
    )

