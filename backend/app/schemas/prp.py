"""SafeZone Patrol Response Point (PRP) Optimization Schemas."""

from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PRPOptimizationRequest(BaseModel):
    mode: str = Field(default="DYNAMIC", description="REFERENCE or DYNAMIC")
    patrol_count: int = Field(default=10, ge=0, le=100, description="Number of available patrol units / PRPs")
    coverage_radius_km: float = Field(default=3.0, gt=0.0, le=20.0, description="Coverage radius in km (3.0 - 5.0 km)")
    time_period: str = Field(default="ALL", description="Target shift: ALL, MORNING, AFTERNOON, EVENING, NIGHT")
    lambda_val: Optional[float] = Field(default=None, description="Custom recency decay lambda parameter")
    start_date: Optional[date] = Field(default=None, description="Optional incident start date filter")
    end_date: Optional[date] = Field(default=None, description="Optional incident end date filter")
    save_run: bool = Field(default=False, description="Persist optimization run and generated PRPs to database")


class PRPLocationResponse(BaseModel):
    id: Optional[int] = None
    optimization_run_id: Optional[int] = None
    rank: int
    prp_type: str
    latitude: float
    longitude: float
    ward_no: int
    zone_no: str
    zone_name: str
    risk_score: float
    coverage_radius_km: float
    status: str = "RECOMMENDED"  # RECOMMENDED, APPROVED, ACTIVE, REJECTED
    covered_demand_count: Optional[int] = 0
    created_at: Optional[datetime] = None


class PRPOptimizationResponse(BaseModel):
    run_id: Optional[int] = None
    run_type: str
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, NO_DATA
    execution_time_seconds: float
    available_patrol_count: int
    coverage_radius_km: float
    total_demand_points: int
    total_weighted_risk: float
    covered_demand_points: int
    covered_weighted_risk: float
    coverage_percentage: float
    uncovered_high_risk_points: int
    selected_prps: List[PRPLocationResponse] = Field(default_factory=list)


class PRPStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Target status: RECOMMENDED, APPROVED, ACTIVE, REJECTED")


class OptimizationRunSummary(BaseModel):
    id: int
    run_type: str
    total_prps_generated: int
    status: str
    execution_time_seconds: Optional[float] = None
    parameters: Optional[Dict[str, Any]] = None
    created_at: datetime
    prps: List[PRPLocationResponse] = Field(default_factory=list)
