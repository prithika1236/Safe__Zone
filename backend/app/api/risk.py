"""SafeZone Geospatial Risk API Endpoints.

Provides endpoints for:
- Ward-level risk assessment and ranking (REFERENCE and DYNAMIC modes)
- Single ward risk inspection with explainable component breakdown
- On-demand custom risk calculation
- Arbitrary point risk evaluation with True Great-Circle spatial radius
- Map-ready GeoJSON feature collections for dashboard map visualization
"""

from datetime import date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.services.risk_service import risk_service
from app.schemas.risk import (
    RiskCalculationRequest,
    PointRiskRequest,
    WardRiskAssessment,
    WardRiskListResponse,
    PointRiskAssessment,
    RiskGeoJSONResponse,
)
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/risk", tags=["Geospatial & Risk Assessment"])


@router.get("/wards", response_model=WardRiskListResponse)
async def list_ward_risks(
    mode: str = Query("DYNAMIC", description="Operational mode: REFERENCE or DYNAMIC"),
    time_period: str = Query("ALL", description="Shift/Time window: ALL, MORNING, AFTERNOON, EVENING, NIGHT"),
    reference_date: Optional[date] = Query(None, description="Reference baseline date"),
    lambda_val: Optional[float] = Query(None, description="Custom recency decay lambda"),
    start_date: Optional[date] = Query(None, description="Filter start date"),
    end_date: Optional[date] = Query(None, description="Filter end date"),
    save_to_db: bool = Query(False, description="Persist scores to database"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve normalized multi-factor risk assessments for all 200 Chennai wards."""
    assessments = await risk_service.calculate_ward_risks(
        db=db,
        mode=mode,
        time_period=time_period,
        reference_date=reference_date,
        lambda_val=lambda_val,
        start_date=start_date,
        end_date=end_date,
        save_to_db=save_to_db,
    )
    return WardRiskListResponse(
        total_wards=len(assessments),
        mode=mode.upper(),
        time_period=time_period.upper(),
        items=assessments,
    )


@router.get("/wards/{ward_no}", response_model=WardRiskAssessment)
async def get_single_ward_risk(
    ward_no: int,
    mode: str = Query("DYNAMIC", description="REFERENCE or DYNAMIC"),
    time_period: str = Query("ALL", description="Shift: ALL, MORNING, AFTERNOON, EVENING, NIGHT"),
    reference_date: Optional[date] = Query(None, description="Reference baseline date"),
    lambda_val: Optional[float] = Query(None, description="Custom recency decay lambda"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve detailed explainable risk assessment for a specific ward number."""
    return await risk_service.get_ward_risk_by_number(
        db=db,
        ward_no=ward_no,
        mode=mode,
        time_period=time_period,
        reference_date=reference_date,
        lambda_val=lambda_val,
    )


@router.post("/calculate", response_model=WardRiskListResponse)
async def calculate_risk_on_demand(
    request: RiskCalculationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger custom on-demand multi-factor risk scoring run."""
    assessments = await risk_service.calculate_ward_risks(
        db=db,
        mode=request.mode,
        time_period=request.time_period,
        reference_date=request.reference_date,
        lambda_val=request.lambda_val,
        start_date=request.start_date,
        end_date=request.end_date,
        save_to_db=request.save_to_db,
    )
    return WardRiskListResponse(
        total_wards=len(assessments),
        mode=request.mode.upper(),
        time_period=request.time_period.upper(),
        items=assessments,
    )


@router.post("/point-risk", response_model=PointRiskAssessment)
async def evaluate_point_risk(
    request: PointRiskRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Evaluate spatial risk at any coordinate using true Haversine distance search."""
    return await risk_service.calculate_point_risk(
        db=db,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        mode=request.mode,
        time_period=request.time_period,
        reference_date=request.reference_date,
        lambda_val=request.lambda_val,
    )


@router.get("/geojson", response_model=RiskGeoJSONResponse)
async def get_risk_geojson(
    mode: str = Query("DYNAMIC", description="REFERENCE or DYNAMIC"),
    time_period: str = Query("ALL", description="Shift: ALL, MORNING, AFTERNOON, EVENING, NIGHT"),
    reference_date: Optional[date] = Query(None, description="Reference baseline date"),
    lambda_val: Optional[float] = Query(None, description="Custom recency decay lambda"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve GeoJSON FeatureCollection of Chennai Wards embedded with computed risk metrics."""
    geojson_data = await risk_service.generate_risk_geojson(
        db=db,
        mode=mode,
        time_period=time_period,
        reference_date=reference_date,
        lambda_val=lambda_val,
    )
    return geojson_data
