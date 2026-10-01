from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import date, time, datetime


# Frozen Severity Mapping
SEVERITY_POLICY = {
    "THEFT": "MEDIUM",
    "ROBBERY": "HIGH",
    "BURGLARY": "HIGH",
    "ASSAULT": "HIGH",
    "STALKING": "MEDIUM",
    "VERBAL_ABUSE_THREAT": "MEDIUM",
    "SEXUAL_HARASSMENT": "HIGH",
    "DOMESTIC_VIOLENCE": "HIGH",
    "KIDNAPPING": "CRITICAL",
    "FRAUD": "MEDIUM",
    "CYBERCRIME": "MEDIUM",
    "VANDALISM": "LOW",
    "DRUG_RELATED_CRIME": "HIGH",
    "PUBLIC_DISTURBANCE": "LOW",
    "HOMICIDE": "CRITICAL",
    "OTHER": "LOW",
}


def derive_time_period(hour: int) -> str:
    if 6 <= hour < 12:
        return "MORNING"
    elif 12 <= hour < 17:
        return "AFTERNOON"
    elif 17 <= hour < 22:
        return "EVENING"
    else:
        return "NIGHT"


class CrimeIncidentCreate(BaseModel):
    description: str = Field(..., min_length=5, description="Natural language incident description")
    crime_category: Optional[str] = Field(None, description="Optional. If omitted, BiLSTM classifier will predict category")
    severity: Optional[str] = Field(None, description="Optional. Defaults to frozen policy for category")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    ward_no: int = Field(..., gt=0)
    zone_no: str = Field(...)
    zone_name: str = Field(...)
    occurred_date: date
    occurred_time: time
    time_period: Optional[str] = None
    location_type: str = Field(default="PUBLIC_PLACE")
    reported_date: Optional[date] = None
    status: Optional[str] = Field(default="REPORTED")


class CrimeIncidentUpdate(BaseModel):
    description: Optional[str] = None
    crime_category: Optional[str] = None
    severity: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    ward_no: Optional[int] = None
    zone_no: Optional[str] = None
    zone_name: Optional[str] = None
    occurred_date: Optional[date] = None
    occurred_time: Optional[time] = None
    time_period: Optional[str] = None
    location_type: Optional[str] = None
    status: Optional[str] = None
    classification_status: Optional[str] = None


class CrimeIncidentVerify(BaseModel):
    crime_category: str = Field(..., description="Confirmed or corrected crime category")
    severity: Optional[str] = Field(None, description="Optional updated severity")


class CrimeIncidentResponse(BaseModel):
    id: int
    crime_id: str
    description: str
    crime_category: str
    severity: str
    latitude: float
    longitude: float
    ward_no: int
    zone_no: str
    zone_name: str
    occurred_date: date
    occurred_time: time
    time_period: str
    location_type: str
    reported_date: date
    status: str
    classification_status: str
    predicted_category: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrimeListResponse(BaseModel):
    items: List[CrimeIncidentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CrimeClassifyPreviewRequest(BaseModel):
    description: str = Field(..., min_length=3)


class CrimeClassifyPreviewResponse(BaseModel):
    description: str
    predicted_category: str
    confidence: float
    classification_status: str
    probabilities: Dict[str, float]


class CSVImportSummary(BaseModel):
    total_rows: int
    imported: int
    skipped_duplicates: int
    failed_rows: int
    errors: List[str] = []
