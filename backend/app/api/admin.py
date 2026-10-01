"""SafeZone Admin Management API.

Provides administrative operations for:
- Creating and onboarding police officers (Public police self-registration is forbidden)
- Managing police officer duty status, ranks, and station assignments
- Creating and configuring patrol vehicle units and resources
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.core.security import require_admin
from app.models.user import User
from app.services.patrol_service import patrol_service
from app.schemas.patrol import (
    PoliceOfficerCreateRequest,
    PoliceOfficerUpdateRequest,
    PoliceOfficerResponse,
    PatrolUnitCreateRequest,
    PatrolUnitUpdateRequest,
    PatrolUnitResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/status")
def admin_status():
    return {"module": "admin", "status": "ready"}


@router.get("/secure-check")
def admin_secure_check(current_user: User = Depends(require_admin)):
    return {
        "message": "Admin authorization verified",
        "admin_email": current_user.email,
        "role": current_user.role,
    }


# ==========================================
# POLICE OFFICER ONBOARDING & MANAGEMENT
# ==========================================

@router.post(
    "/police",
    response_model=PoliceOfficerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Police Officer Account (Admin Only)",
)
async def create_police_officer(
    request: PoliceOfficerCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin creates verified Police Officer account with login credentials."""
    return await patrol_service.create_police_officer(db=db, req=request)


@router.get(
    "/police",
    response_model=List[PoliceOfficerResponse],
    summary="List Police Officers (Admin Only)",
)
async def list_police_officers(
    station_name: Optional[str] = Query(None, description="Filter by station name"),
    on_duty: Optional[bool] = Query(None, description="Filter by on_duty status"),
    is_available: Optional[bool] = Query(None, description="Filter by availability"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """List all police officers with optional duty/availability filters."""
    return await patrol_service.list_police_officers(
        db=db, station_name=station_name, on_duty=on_duty, is_available=is_available
    )


@router.put(
    "/police/{officer_id}",
    response_model=PoliceOfficerResponse,
    summary="Update Police Officer Profile (Admin Only)",
)
async def update_police_officer(
    officer_id: int,
    request: PoliceOfficerUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Update officer rank, duty status, station, or user profile information."""
    return await patrol_service.update_police_officer(db=db, officer_id=officer_id, req=request)


# ==========================================
# PATROL UNIT RESOURCE MANAGEMENT
# ==========================================

@router.post(
    "/patrol-units",
    response_model=PatrolUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Patrol Unit Resource (Admin Only)",
)
async def create_patrol_unit(
    request: PatrolUnitCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Register a new patrol vehicle or unit resource."""
    return await patrol_service.create_patrol_unit(db=db, req=request)


@router.get(
    "/patrol-units",
    response_model=List[PatrolUnitResponse],
    summary="List Patrol Units (Admin Only)",
)
async def list_patrol_units(
    status_filter: Optional[str] = Query(None, alias="status", description="AVAILABLE, DISPATCHED, ON_PATROL, OFF_DUTY"),
    unit_type: Optional[str] = Query(None, description="VEHICLE, MOTORCYCLE, FOOT"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """List patrol units with status and vehicle type filters."""
    return await patrol_service.list_patrol_units(db=db, status_filter=status_filter, unit_type=unit_type)


@router.put(
    "/patrol-units/{unit_id}",
    response_model=PatrolUnitResponse,
    summary="Update Patrol Unit (Admin Only)",
)
async def update_patrol_unit(
    unit_id: int,
    request: PatrolUnitUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Update patrol unit status or location."""
    return await patrol_service.update_patrol_unit(db=db, unit_id=unit_id, req=request)
