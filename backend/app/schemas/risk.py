"""SafeZone Risk Assessment and Geospatial Schemas."""

from datetime import date, datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class RiskCalculationRequest(BaseModel):
    mode: str = Field(default="DYNAMIC", description="REFERENCE or DYNAMIC")
    time_period: str = Field(default="ALL", description="ALL, MORNING, AFTERNOON, EVENING, NIGHT")
    reference_date: Optional[date] = Field(default=None, description="Reference baseline date")
    lambda_val: Optional[float] = Field(default=None, description="Custom recency decay lambda")
    start_date: Optional[date] = Field(default=None, description="Optional filter start date")
    end_date: Optional[date] = Field(default=None, description="Optional filter end date")
    save_to_db: bool = Field(default=False, description="Persist calculated risk scores to database")


class PointRiskRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude of target location")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude of target location")
    radius_km: float = Field(default=1.5, gt=0.0, le=20.0, description="Search radius in kilometers")
    mode: str = Field(default="DYNAMIC", description="REFERENCE or DYNAMIC")
    time_period: str = Field(default="ALL", description="ALL, MORNING, AFTERNOON, EVENING, NIGHT")
    reference_date: Optional[date] = Field(default=None, description="Reference baseline date")
    lambda_val: Optional[float] = Field(default=None, description="Recency decay parameter")


class WardRiskAssessment(BaseModel):
    ward_no: int
    zone_no: str
    zone_name: str
    mode: str
    time_period: str
    raw_risk_score: float
    normalized_risk_score: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    incident_count: int
    frequency_component: float
    severity_component: float
    recency_component: float
    time_component: float
    dominant_category: str
    category_counts: Dict[str, int] = Field(default_factory=dict)
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None


class WardRiskListResponse(BaseModel):
    total_wards: int
    mode: str
    time_period: str
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    items: List[WardRiskAssessment]


class PointRiskAssessment(BaseModel):
    latitude: float
    longitude: float
    radius_km: float
    mode: str
    time_period: str
    ward_no: Optional[int] = None
    zone_no: Optional[str] = None
    zone_name: Optional[str] = None
    raw_risk_score: float
    risk_level: str
    incident_count: int
    frequency_component: float
    severity_component: float
    recency_component: float
    time_component: float
    dominant_category: str
    category_counts: Dict[str, int] = Field(default_factory=dict)


class RiskGeoJSONResponse(BaseModel):
    type: str = "FeatureCollection"
    features: List[Dict[str, Any]]
    crs: Optional[Dict[str, Any]] = None
