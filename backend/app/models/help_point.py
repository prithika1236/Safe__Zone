from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime
)
from geoalchemy2 import Geometry
from app.database.base import Base


class SafeHelpPoint(Base):
    __tablename__ = "safe_help_points"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    facility_type = Column(String(100), nullable=False)  # HOSPITAL, POLICE_STATION, EMERGENCY_FACILITY
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    address = Column(Text, nullable=True)
    phone_number = Column(String(50), nullable=True)
    is_verified = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
