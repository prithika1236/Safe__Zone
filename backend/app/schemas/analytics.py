"""SafeZone Analytics and Academic Evaluation Schemas.

Defines schemas for:
- Reference vs Dynamic vs Baseline strategy evaluation metrics
- Grounded coverage, weighted risk, and geodesic distance indicators
- Real-time operational summary metrics
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StrategyEvaluationMetric(BaseModel):
    """Comparative performance indicators for a single patrol deployment strategy."""
    name: str = Field(..., description="Display name of the strategy")
    strategy_type: str = Field(..., description="REFERENCE, DYNAMIC, or RANDOM")
    patrol_count: int = Field(..., description="Number of allocated patrol units/PRPs")
    total_demand_points: int = Field(..., description="Total demand points in evaluation set")
    covered_demand_points: int = Field(..., description="Unique demand points within coverage radius")
    coverage_percentage: float = Field(..., description="Percentage of demand points covered")
    total_weighted_risk: float = Field(..., description="Sum of weighted risk of all demand points")
    covered_weighted_risk: float = Field(..., description="Sum of weighted risk covered without double-counting")
    weighted_risk_coverage_pct: float = Field(..., description="Percentage of total weighted risk covered")
    high_risk_total: int = Field(..., description="Number of high-risk demand points (weight >= 2.0)")
    high_risk_covered: int = Field(..., description="Number of high-risk demand points covered")
    high_risk_coverage_pct: float = Field(..., description="Percentage of high-risk points covered")
    mean_distance_km: float = Field(..., description="Mean geodesic distance from demand points to nearest PRP")
    max_distance_km: float = Field(..., description="Maximum geodesic distance from demand points to nearest PRP")
    estimated_response_time_min: Optional[float] = Field(
        None, description="Omitted unless verified routing duration is available"
    )


class EvaluationRequest(BaseModel):
    """Evaluation parameters for strategy comparison."""
    patrol_count: int = Field(10, ge=1, le=50, description="Patrol / PRP deployment budget (K)")
    coverage_radius_km: float = Field(3.0, ge=0.5, le=15.0, description="Spatial coverage radius in km")
    time_period: str = Field("ALL", description="Shift filter: ALL, MORNING, AFTERNOON, EVENING, NIGHT")
    use_stored_prps_if_available: bool = Field(
        True, description="Prefer evaluating existing stored optimization runs if available"
    )


class EvaluationComparisonResponse(BaseModel):
    """Complete comparative evaluation response between Reference and Dynamic PRPs."""
    reference: StrategyEvaluationMetric = Field(..., description="Long-term historical reference strategy")
    dynamic: StrategyEvaluationMetric = Field(..., description="Time-sensitive dynamic SafeZone strategy")
    random_baseline: Optional[StrategyEvaluationMetric] = Field(
        None, description="Reproducible random candidate baseline (seed=42)"
    )
    dataset_incident_count: int = Field(..., description="Number of incidents in evaluation dataset")
    coverage_radius_km: float = Field(..., description="Evaluated coverage radius in km")
    patrol_count: int = Field(..., description="Evaluated patrol budget")
    time_period: str = Field(..., description="Evaluated shift window")
    high_risk_threshold_description: str = Field(
        "Incident risk weight >= 2.0 (High / Critical severity threshold)",
        description="Documentation of high-risk threshold derivation"
    )
    distance_method: str = Field(
        "Geodesic (Haversine) distance from demand points to nearest PRP",
        description="Distance calculation method"
    )
    data_source: str = Field(
        "SafeZone Prototype Dataset (Chennai Municipal Wards 1-200)",
        description="Source dataset description"
    )
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class OperationalSummaryResponse(BaseModel):
    """Live operational state of SafeZone resources and incidents."""
    total_crimes: int
    total_patrol_units: int
    on_duty_patrols: int
    available_patrols: int
    dispatched_patrols: int
    active_prps: int
    active_sos_incidents: int
    total_help_points: int
    category_counts: Dict[str, int]
    severity_counts: Dict[str, int]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
