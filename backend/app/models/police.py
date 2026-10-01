from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.database.base import Base


class PoliceOfficer(Base):
    __tablename__ = "police_officers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    badge_number = Column(String(50), unique=True, index=True, nullable=False)
    rank = Column(String(100), nullable=False)
    station_name = Column(String(255), nullable=False)
    on_duty = Column(Boolean, default=False, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="police_profile")
    assignments = relationship("PatrolAssignment", back_populates="officer")
    sos_dispatches = relationship("SOSRequest", back_populates="assigned_officer", foreign_keys="SOSRequest.assigned_officer_id")
    location_logs = relationship("LocationUpdate", back_populates="officer")


class PatrolUnit(Base):
    __tablename__ = "patrol_units"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    unit_code = Column(String(50), unique=True, index=True, nullable=False)
    unit_type = Column(String(50), default="VEHICLE", nullable=False)  # VEHICLE, MOTORCYCLE, FOOT
    status = Column(String(50), default="AVAILABLE", nullable=False)    # AVAILABLE, DISPATCHED, ON_PATROL, OFF_DUTY
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    last_location_update = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    assignments = relationship("PatrolAssignment", back_populates="patrol_unit")
    sos_dispatches = relationship("SOSRequest", back_populates="assigned_patrol", foreign_keys="SOSRequest.assigned_patrol_id")
    location_logs = relationship("LocationUpdate", back_populates="patrol_unit")


class LocationUpdate(Base):
    __tablename__ = "location_updates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patrol_unit_id = Column(Integer, ForeignKey("patrol_units.id", ondelete="SET NULL"), nullable=True, index=True)
    officer_id = Column(Integer, ForeignKey("police_officers.id", ondelete="SET NULL"), nullable=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    patrol_unit = relationship("PatrolUnit", back_populates="location_logs")
    officer = relationship("PoliceOfficer", back_populates="location_logs")
