"""SafeZone Geospatial and Risk Engine Test Suite.

Verifies:
- Recent crime contributes more than otherwise identical old crime (exponential recency decay)
- Severity weighting hierarchy (HIGH > MEDIUM > LOW)
- Time-of-day / Shift relevance matching
- Safe handling of empty datasets (no zero-division)
- REFERENCE mode vs DYNAMIC mode operational behavior
- Spatial cohort normalization strictly bounded in [0.0, 1.0]
- True Great-Circle Haversine distance and polygon containment
- API Endpoints: /api/v1/risk/wards, /api/v1/risk/point-risk, /api/v1/risk/geojson
"""

import math
import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.models.crime import CrimeIncident
from app.core.security import get_password_hash, create_access_token
from app.services.location_service import location_service
from app.optimization.risk_scoring import (
    risk_scoring_engine,
    IncidentInput,
    RiskScoringEngine,
)


@pytest_asyncio.fixture
async def admin_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        admin = User(
            email="admin_risk@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Risk Admin Officer",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


# ==========================================
# 1. MATHEMATICAL ENGINE UNIT TESTS
# ==========================================

def test_recency_exponential_decay():
    """Verify that a recent crime contributes more than an otherwise identical old crime."""
    ref_date = date(2026, 9, 20)
    recent_date = date(2026, 9, 19)  # 1 day old
    old_date = date(2026, 7, 22)     # 60 days old

    recent_inc = IncidentInput(
        crime_category="ROBBERY",
        severity="HIGH",
        occurred_date=recent_date,
        time_period="NIGHT",
    )
    old_inc = IncidentInput(
        crime_category="ROBBERY",
        severity="HIGH",
        occurred_date=old_date,
        time_period="NIGHT",
    )

    recent_score = risk_scoring_engine.score_single_incident(
        recent_inc, mode="DYNAMIC", reference_date=ref_date, lambda_val=0.05
    )
    old_score = risk_scoring_engine.score_single_incident(
        old_inc, mode="DYNAMIC", reference_date=ref_date, lambda_val=0.05
    )

    assert recent_score["total_contribution"] > old_score["total_contribution"]
    # 1-day weight ~ exp(-0.05*1) = 0.9512
    # 60-day weight ~ exp(-0.05*60) = 0.0498
    assert recent_score["recency_weight"] > 0.90
    assert old_score["recency_weight"] < 0.10


def test_severity_weighting():
    """Verify that severity grades correctly scale risk (HIGH > MEDIUM > LOW)."""
    ref_date = date(2026, 9, 20)
    high_inc = IncidentInput(crime_category="ASSAULT", severity="HIGH", occurred_date=ref_date)
    med_inc = IncidentInput(crime_category="ASSAULT", severity="MEDIUM", occurred_date=ref_date)
    low_inc = IncidentInput(crime_category="ASSAULT", severity="LOW", occurred_date=ref_date)

    score_high = risk_scoring_engine.score_single_incident(high_inc, reference_date=ref_date)
    score_med = risk_scoring_engine.score_single_incident(med_inc, reference_date=ref_date)
    score_low = risk_scoring_engine.score_single_incident(low_inc, reference_date=ref_date)

    assert score_high["severity_weight"] > score_med["severity_weight"]
    assert score_med["severity_weight"] > score_low["severity_weight"]
    assert score_high["total_contribution"] > score_med["total_contribution"] > score_low["total_contribution"]


def test_time_shift_relevance():
    """Verify that an incident during the target shift receives higher weight than non-matching shift."""
    ref_date = date(2026, 9, 20)
    night_inc = IncidentInput(crime_category="BURGLARY", severity="HIGH", occurred_date=ref_date, time_period="NIGHT")
    morning_inc = IncidentInput(crime_category="BURGLARY", severity="HIGH", occurred_date=ref_date, time_period="MORNING")

    # Target shift: NIGHT
    score_night = risk_scoring_engine.score_single_incident(night_inc, reference_date=ref_date, target_shift="NIGHT")
    score_morning = risk_scoring_engine.score_single_incident(morning_inc, reference_date=ref_date, target_shift="NIGHT")

    assert score_night["time_weight"] == 1.5
    assert score_morning["time_weight"] == 0.5
    assert score_night["total_contribution"] > score_morning["total_contribution"]

    # Target shift: ALL
    score_all = risk_scoring_engine.score_single_incident(night_inc, reference_date=ref_date, target_shift="ALL")
    assert score_all["time_weight"] == 1.0


def test_empty_dataset_handling():
    """Verify that scoring an empty list returns safe zero-risk without division-by-zero."""
    breakdown = risk_scoring_engine.compute_risk_for_incidents([])
    assert breakdown.incident_count == 0
    assert breakdown.raw_score == 0.0
    assert breakdown.normalized_score == 0.0
    assert breakdown.risk_level == "LOW"
    assert breakdown.frequency_component == 0.0
    assert breakdown.severity_component == 0.0
    assert breakdown.recency_component == 0.0
    assert breakdown.time_component == 0.0
    assert breakdown.dominant_category == "NONE"


def test_reference_vs_dynamic_modes():
    """Verify REFERENCE mode uses lambda=0 (no recency decay) while DYNAMIC mode applies decay."""
    ref_date = date(2026, 9, 20)
    old_date = date(2025, 9, 20)  # 365 days ago

    old_inc = IncidentInput(crime_category="THEFT", severity="MEDIUM", occurred_date=old_date)

    # In REFERENCE mode, 365-day-old crime has full recency weight (1.0)
    ref_score = risk_scoring_engine.score_single_incident(old_inc, mode="REFERENCE", reference_date=ref_date)
    assert ref_score["recency_weight"] == 1.0

    # In DYNAMIC mode, 365-day-old crime decays toward 0.0
    dyn_score = risk_scoring_engine.score_single_incident(old_inc, mode="DYNAMIC", reference_date=ref_date, lambda_val=0.05)
    assert dyn_score["recency_weight"] < 0.001


def test_cohort_normalization():
    """Verify Min-Max cohort normalization scales raw scores strictly into [0.0, 1.0]."""
    ref_date = date(2026, 9, 20)

    # Simulate 3 wards with different crime profiles
    w1_inc = [IncidentInput(crime_category="HOMICIDE", severity="HIGH", occurred_date=ref_date)] * 5
    w2_inc = [IncidentInput(crime_category="THEFT", severity="LOW", occurred_date=ref_date)] * 2
    w3_inc = []

    cohort = {
        1: risk_scoring_engine.compute_risk_for_incidents(w1_inc, reference_date=ref_date),
        2: risk_scoring_engine.compute_risk_for_incidents(w2_inc, reference_date=ref_date),
        3: risk_scoring_engine.compute_risk_for_incidents(w3_inc, reference_date=ref_date),
    }

    normalized = risk_scoring_engine.normalize_cohort_scores(cohort)

    assert normalized[1].normalized_score == 1.0
    assert normalized[1].risk_level == "CRITICAL"

    assert 0.0 <= normalized[2].normalized_score <= 1.0

    assert normalized[3].normalized_score == 0.0
    assert normalized[3].risk_level == "LOW"


# ==========================================
# 2. GEOSPATIAL & LOCATION SERVICE TESTS
# ==========================================

def test_haversine_distance_calculation():
    """Verify Haversine Great-Circle distance between Chennai landmark coordinates."""
    # Chennai Central (13.0827, 80.2707) to Marina Beach (13.0500, 80.2824)
    dist_km = location_service.haversine_distance(13.0827, 80.2707, 13.0500, 80.2824)
    # True spherical distance is approx 3.84 km
    assert 3.5 <= dist_km <= 4.2

    # Distance to identical point is 0
    assert location_service.haversine_distance(13.0827, 80.2707, 13.0827, 80.2707) == 0.0

    # Distance in meters
    dist_m = location_service.haversine_distance_meters(13.0827, 80.2707, 13.0500, 80.2824)
    assert 3500 <= dist_m <= 4200


def test_ward_containment_and_metadata():
    """Verify Chennai ward lookup from polygon geometry in Wards.geojson."""
    # Coordinate inside Ward 119 (Teynampet): 13.0450, 80.2650
    ward_meta = location_service.find_ward_for_coordinate(13.0450, 80.2650)
    assert ward_meta is not None
    assert ward_meta["ward_no"] == 119
    assert ward_meta["zone_name"] == "TEYNAMPET"
    assert "centroid_lat" in ward_meta
    assert "centroid_lon" in ward_meta


def test_points_within_coverage_radius():
    """Verify spatial coverage radius filtering."""
    center_lat, center_lon = 13.0827, 80.2707
    test_points = [
        (13.0827, 80.2707),  # 0 km (Inside)
        (13.0850, 80.2720),  # ~0.3 km (Inside)
        (13.1500, 80.2707),  # ~7.5 km (Outside 3km)
    ]
    covered = location_service.get_points_within_radius(center_lat, center_lon, test_points, radius_km=3.0)
    assert 0 in covered
    assert 1 in covered
    assert 2 not in covered


# ==========================================
# 3. FASTAPI API ROUTE INTEGRATION TESTS
# ==========================================

@pytest.mark.asyncio
async def test_api_list_ward_risks(async_client: AsyncClient, admin_auth_header: dict):
    """Verify GET /api/v1/risk/wards endpoint returns all 200 wards with valid schema."""
    from tests.conftest import TestAsyncSessionLocal

    # Insert sample incidents
    async with TestAsyncSessionLocal() as session:
        c1 = CrimeIncident(
            crime_id="CR-RISK-001",
            description="Armed robbery at street shop.",
            crime_category="ROBBERY",
            severity="HIGH",
            latitude=13.0450,
            longitude=80.2650,
            ward_no=119,
            zone_no="IX",
            zone_name="TEYNAMPET",
            occurred_date=date.today(),
            occurred_time=time(21, 0),
            time_period="EVENING",
            location_type="SHOPPING_MALL",
            reported_date=date.today(),
            status="REPORTED",
            classification_status="AUTO_CLASSIFIED",
        )
        session.add(c1)
        await session.commit()

    response = await async_client.get("/api/v1/risk/wards?mode=DYNAMIC&time_period=ALL", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["total_wards"] >= 200
    assert data["mode"] == "DYNAMIC"
    assert len(data["items"]) >= 200

    # Verify Ward 119 is ranked at or near top
    ward_119 = next((w for w in data["items"] if w["ward_no"] == 119), None)
    assert ward_119 is not None
    assert ward_119["incident_count"] >= 1
    assert ward_119["dominant_category"] == "ROBBERY"
    assert ward_119["normalized_risk_score"] > 0.0


@pytest.mark.asyncio
async def test_api_single_ward_risk(async_client: AsyncClient, admin_auth_header: dict):
    """Verify GET /api/v1/risk/wards/{ward_no} returns detailed breakdown."""
    response = await async_client.get("/api/v1/risk/wards/119", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["ward_no"] == 119
    assert data["zone_name"] == "TEYNAMPET"
    assert "raw_risk_score" in data
    assert "normalized_risk_score" in data
    assert "risk_level" in data
    assert "frequency_component" in data
    assert "severity_component" in data
    assert "recency_component" in data
    assert "time_component" in data


@pytest.mark.asyncio
async def test_api_point_risk_evaluation(async_client: AsyncClient, admin_auth_header: dict):
    """Verify POST /api/v1/risk/point-risk calculates localized risk at coordinates."""
    payload = {
        "latitude": 13.0450,
        "longitude": 80.2650,
        "radius_km": 2.0,
        "mode": "DYNAMIC",
        "time_period": "ALL",
    }
    response = await async_client.post("/api/v1/risk/point-risk", json=payload, headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == 13.0450
    assert data["longitude"] == 80.2650
    assert data["ward_no"] == 119
    assert "raw_risk_score" in data
    assert "risk_level" in data


@pytest.mark.asyncio
async def test_api_risk_geojson(async_client: AsyncClient, admin_auth_header: dict):
    """Verify GET /api/v1/risk/geojson returns valid GeoJSON FeatureCollection with embedded risk."""
    response = await async_client.get("/api/v1/risk/geojson?mode=REFERENCE", headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 200

    first_feat = data["features"][0]
    assert "geometry" in first_feat
    assert "properties" in first_feat
    props = first_feat["properties"]
    assert "Ward_No" in props
    assert "Zone_Name" in props
    assert "raw_risk_score" in props
    assert "normalized_risk_score" in props
    assert "risk_level" in props
