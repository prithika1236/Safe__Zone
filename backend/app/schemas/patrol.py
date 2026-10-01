"""SafeZone Police, Patrol Resource and PRP Assignment Schemas."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# ==========================================
# POLICE OFFICER SCHEMAS
# ==========================================

class PoliceOfficerCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone_number: Optional[str] = None
    badge_number: str = Field(..., min_length=2)
    rank: str = Field(default="Constable")
    station_name: str = Field(default="Central Police Station")
    on_duty: bool = Field(default=False)


class PoliceOfficerUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    rank: Optional[str] = None
    station_name: Optional[str] = None
    on_duty: Optional[bool] = None
    is_available: Optional[bool] = None
    is_active: Optional[bool] = None


class PoliceOfficerResponse(BaseModel):
    id: int
    user_id: int
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None
    badge_number: str
    rank: str
    station_name: str
    on_duty: bool
    is_available: bool
    is_active: bool
    created_at: datetime


# ==========================================
# PATROL UNIT SCHEMAS
# ==========================================

class PatrolUnitCreateRequest(BaseModel):
    unit_code: str = Field(..., min_length=2)
    unit_type: str = Field(default="VEHICLE", description="VEHICLE, MOTORCYCLE, FOOT")
    status: str = Field(default="AVAILABLE", description="AVAILABLE, DISPATCHED, ON_PATROL, OFF_DUTY")
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None


class PatrolUnitUpdateRequest(BaseModel):
    unit_type: Optional[str] = None
    status: Optional[str] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None


class PatrolUnitResponse(BaseModel):
    id: int
    unit_code: str
    unit_type: str
    status: str
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    last_location_update: Optional[datetime] = None
    created_at: datetime


# ==========================================
# PATROL ASSIGNMENT SCHEMAS
# ==========================================

class ManualAssignmentRequest(BaseModel):
    prp_id: int
    patrol_unit_id: int
    officer_id: int
    shift_start: Optional[datetime] = None
    shift_end: Optional[datetime] = None


class AutoAssignmentRequest(BaseModel):
    optimization_run_id: Optional[int] = None
    shift_start: Optional[datetime] = None
    shift_end: Optional[datetime] = None


class AssignmentStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="ASSIGNED, ACKNOWLEDGED, AT_PRP, UNAVAILABLE, COMPLETED, CANCELLED")


class PatrolAssignmentResponse(BaseModel):
    id: int
    prp_id: int
    patrol_unit_id: Optional[int] = None
    officer_id: Optional[int] = None
    shift_start: datetime
    shift_end: datetime
    status: str  # ASSIGNED, ACKNOWLEDGED, AT_PRP, UNAVAILABLE, COMPLETED, CANCELLED
    created_at: datetime
    updated_at: datetime
    prp_details: Optional[Dict[str, Any]] = None
    patrol_unit_details: Optional[Dict[str, Any]] = None
    officer_details: Optional[Dict[str, Any]] = None


class AutoAssignmentResponse(BaseModel):
    status: str
    total_target_prps: int
    assigned_count: int
    unassigned_prps_count: int
    assignments: List[PatrolAssignmentResponse] = Field(default_factory=list)


class DutyStatusUpdateRequest(BaseModel):
    on_duty: bool
    is_available: Optional[bool] = None


class LocationUpdateRequest(BaseModel):
    latitude: float
    longitude: float

