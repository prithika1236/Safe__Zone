from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.database.base import Base


class SOSRequest(Base):
    __tablename__ = "sos_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    citizen_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    status = Column(String(50), default="ACTIVE", nullable=False, index=True)  # ACTIVE, EN_ROUTE, ARRIVED, RESOLVED, CANCELLED
    assigned_patrol_id = Column(Integer, ForeignKey("patrol_units.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_officer_id = Column(Integer, ForeignKey("police_officers.id", ondelete="SET NULL"), nullable=True, index=True)
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    citizen = relationship("User", back_populates="sos_requests", foreign_keys=[citizen_id])
    assigned_patrol = relationship("PatrolUnit", back_populates="sos_dispatches", foreign_keys=[assigned_patrol_id])
    assigned_officer = relationship("PoliceOfficer", back_populates="sos_dispatches", foreign_keys=[assigned_officer_id])
