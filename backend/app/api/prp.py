"""SafeZone Patrol Response Point (PRP) Optimization API.

Provides endpoints for:
- Solving Maximum Crime-Risk Coverage optimization runs (REFERENCE and DYNAMIC modes)
- Inspecting optimization run metrics and generated PRPs
- Approving, activating, and rejecting PRP deployment recommendations
- Listing active patrol response points for police patrol dispatch
- Strict Privacy: Exact PRP locations are restricted to POLICE and ADMIN roles only (Citizens are blocked).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.services.prp_service import prp_service
from app.schemas.prp import (
    PRPOptimizationRequest,
    PRPOptimizationResponse,
    PRPLocationResponse,
    PRPStatusUpdateRequest,
    OptimizationRunSummary,
)
from app.core.security import require_admin, require_police
from app.models.user import User

router = APIRouter(prefix="/prp", tags=["Patrol Response Points (PRP)"])


@router.get("/status")
def prp_status():
    return {"module": "prp", "status": "ready"}



@router.post(
    "/optimize",
    response_model=PRPOptimizationResponse,
    summary="Preview or Run PRP Optimization (Admin Only)",
)
async def optimize_prp_deployment(
    request: PRPOptimizationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Run Google OR-Tools Maximum Coverage optimization on demand.
    
    Supports both REFERENCE (historical baseline) and DYNAMIC (real-time operational) modes.
    """
    return await prp_service.run_optimization(db=db, request=request)


@router.post(
    "/runs",
    response_model=PRPOptimizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute and Persist Optimization Run (Admin Only)",
)
async def create_optimization_run(
    request: PRPOptimizationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Execute optimization run and persist run metadata and generated PRPs to database."""
    request.save_run = True
    return await prp_service.run_optimization(db=db, request=request)


@router.get(
    "/runs",
    response_model=List[OptimizationRunSummary],
    summary="List Historical Optimization Runs (Police & Admin)",
)
async def list_optimization_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Retrieve paginated list of past optimization runs."""
    return await prp_service.list_optimization_runs(db=db, skip=skip, limit=limit)


@router.get(
    "/runs/{run_id}",
    response_model=OptimizationRunSummary,
    summary="Get Optimization Run Details (Police & Admin)",
)
async def get_optimization_run(
    run_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """Retrieve details and generated PRPs for a specific optimization run."""
    run = await prp_service.get_optimization_run(db=db, run_id=run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization run #{run_id} not found.",
        )
    return run


@router.post(
    "/{prp_id}/status",
    response_model=PRPLocationResponse,
    summary="Update PRP Deployment Status (Admin Only)",
)
async def update_prp_status(
    prp_id: int,
    request: PRPStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Transition PRP status: RECOMMENDED -> APPROVED -> ACTIVE / REJECTED."""
    valid_statuses = ["RECOMMENDED", "APPROVED", "ACTIVE", "REJECTED"]
    if request.status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{request.status}'. Allowed: {valid_statuses}",
        )

    updated_prp = await prp_service.update_prp_status(
        db=db, prp_id=prp_id, new_status=request.status
    )
    if not updated_prp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PRP #{prp_id} not found.",
        )
    return updated_prp


@router.get(
    "/active",
    response_model=List[PRPLocationResponse],
    summary="List Active Patrol Response Points (Police & Admin)",
)
async def list_active_prps(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_police),
):
    """List currently active and approved PRPs for dispatch.
    
    RESTRICTED: Exact PRP coordinates are inaccessible to Citizen roles.
    """
    return await prp_service.list_active_prps(db=db)
