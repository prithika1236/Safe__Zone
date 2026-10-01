from datetime import datetime, date, time
from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, Time, DateTime
)
from geoalchemy2 import Geometry
from app.database.base import Base


class CrimeIncident(Base):
    __tablename__ = "crime_incidents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    crime_id = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    crime_category = Column(String(100), index=True, nullable=False)
    severity = Column(String(50), index=True, nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    ward_no = Column(Integer, index=True, nullable=False)
    zone_no = Column(String(50), index=True, nullable=False)
    zone_name = Column(String(100), nullable=False)
    occurred_date = Column(Date, index=True, nullable=False)
    occurred_time = Column(Time, nullable=False)
    time_period = Column(String(50), index=True, nullable=False)  # MORNING, AFTERNOON, EVENING, NIGHT
    location_type = Column(String(100), nullable=False)
    reported_date = Column(Date, nullable=False)
    status = Column(String(50), default="REPORTED", nullable=False)

    # Classification Review & ML Metadata
    classification_status = Column(String(50), default="AUTO_CLASSIFIED", nullable=False)  # AUTO_CLASSIFIED, REVIEW_REQUIRED, ADMIN_VERIFIED
    predicted_category = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
