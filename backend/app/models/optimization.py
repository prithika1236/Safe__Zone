from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.database.base import Base


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_type = Column(String(50), nullable=False)  # REFERENCE, DYNAMIC
    parameters = Column(JSON, nullable=True)
    total_prps_generated = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="COMPLETED", nullable=False)  # COMPLETED, FAILED
    execution_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    prps = relationship("PRPLocation", back_populates="optimization_run", cascade="all, delete-orphan")


class PRPLocation(Base):
    __tablename__ = "prp_locations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    optimization_run_id = Column(Integer, ForeignKey("optimization_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    prp_type = Column(String(50), nullable=False)  # REFERENCE, DYNAMIC
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geom = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=True)
    ward_no = Column(Integer, index=True, nullable=False)
    zone_no = Column(String(50), index=True, nullable=False)
    zone_name = Column(String(100), nullable=False)
    rank = Column(Integer, nullable=False)
    risk_score = Column(Float, nullable=False)
    coverage_radius_km = Column(Float, default=3.0, nullable=False)
    status = Column(String(50), default="RECOMMENDED", nullable=False)  # RECOMMENDED, APPROVED, ACTIVE, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    optimization_run = relationship("OptimizationRun", back_populates="prps")
    assignments = relationship("PatrolAssignment", back_populates="prp")


class PatrolAssignment(Base):
    __tablename__ = "patrol_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    prp_id = Column(Integer, ForeignKey("prp_locations.id", ondelete="CASCADE"), nullable=False, index=True)
    patrol_unit_id = Column(Integer, ForeignKey("patrol_units.id", ondelete="SET NULL"), nullable=True, index=True)
    officer_id = Column(Integer, ForeignKey("police_officers.id", ondelete="SET NULL"), nullable=True, index=True)
    shift_start = Column(DateTime, nullable=False)
    shift_end = Column(DateTime, nullable=False)
    status = Column(String(50), default="ASSIGNED", nullable=False)  # ASSIGNED, ACTIVE, COMPLETED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    prp = relationship("PRPLocation", back_populates="assignments")
    patrol_unit = relationship("PatrolUnit", back_populates="assignments")
    officer = relationship("PoliceOfficer", back_populates="assignments")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ward_no = Column(Integer, index=True, nullable=False)
    zone_no = Column(String(50), index=True, nullable=False)
    risk_type = Column(String(50), nullable=False)  # REFERENCE, DYNAMIC
    base_risk = Column(Float, nullable=False)
    time_period = Column(String(50), default="ALL", nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(JSON, nullable=True)
