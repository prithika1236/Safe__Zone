import pytest
from app.database.base import Base
from app.models import (
    User, UserRole, EmergencyContact,
    PoliceOfficer, PatrolUnit, LocationUpdate,
    CrimeIncident, SOSRequest,
    OptimizationRun, PRPLocation, PatrolAssignment, RiskScore,
    SafeHelpPoint,
)


def test_all_entities_in_metadata():
    expected_tables = {
        "users",
        "emergency_contacts",
        "police_officers",
        "patrol_units",
        "location_updates",
        "crime_incidents",
        "sos_requests",
        "optimization_runs",
        "prp_locations",
        "patrol_assignments",
        "risk_scores",
        "safe_help_points",
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - actual_tables
    assert not missing_tables, f"Missing required database tables: {missing_tables}"


def test_user_roles():
    assert UserRole.ADMIN == "ADMIN"
    assert UserRole.POLICE == "POLICE"
    assert UserRole.CITIZEN == "CITIZEN"


def test_crime_incident_columns():
    table = Base.metadata.tables["crime_incidents"]
    column_names = {c.name for c in table.columns}
    required_cols = {
        "id", "crime_id", "description", "crime_category", "severity",
        "latitude", "longitude", "ward_no", "zone_no", "zone_name",
        "occurred_date", "occurred_time", "time_period",
        "location_type", "reported_date", "status",
        "classification_status", "predicted_category", "confidence",
        "created_at", "updated_at"
    }
    assert required_cols.issubset(column_names)


def test_sos_request_columns():
    table = Base.metadata.tables["sos_requests"]
    column_names = {c.name for c in table.columns}
    assert {"citizen_id", "status", "assigned_patrol_id", "assigned_officer_id", "triggered_at"}.issubset(column_names)


def test_prp_location_columns():
    table = Base.metadata.tables["prp_locations"]
    column_names = {c.name for c in table.columns}
    assert {"prp_type", "latitude", "longitude", "ward_no", "rank", "risk_score", "coverage_radius_km", "status"}.issubset(column_names)


def test_safe_help_point_columns():
    table = Base.metadata.tables["safe_help_points"]
    column_names = {c.name for c in table.columns}
    assert {"name", "facility_type", "latitude", "longitude", "is_verified", "is_active"}.issubset(column_names)
