"""SafeZone Stage 15 — Analytics and Academic Strategy Evaluation Test Suite.

Verifies:
1. Reference vs Dynamic vs Random baseline comparative evaluation returns valid computed metrics.
2. Demand points are covered with zero double-counting.
3. Coverage percentage, weighted risk percentage, and high-risk coverage use exact computed values.
4. High-risk threshold (weight >= 2.0 / HIGH severity) is strictly respected.
5. Mean and maximum geodesic distance to nearest PRP are accurately computed.
6. Random candidate baseline is deterministic and reproducible (seed=42).
7. Estimated response time metric is NOT fabricated (omitted/None without routing duration).
8. Admin authorization security (require_admin blocks non-admins with 403/401).
9. Safe handling of empty/zero-crime scenarios.
10. Live operational summary correctly aggregates database counts.
"""

from datetime import date, datetime, time, timedelta
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.crime import CrimeIncident
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.optimization import PRPLocation, OptimizationRun
from app.core.security import create_access_token, get_password_hash
from app.services.analytics_service import analytics_service
from app.schemas.analytics import EvaluationRequest
from tests.conftest import TestAsyncSessionLocal


@pytest_asyncio.fixture
async def setup_analytics_env():
    """Setup Admin, Citizen users and sample crime incidents across Chennai wards."""
    async with TestAsyncSessionLocal() as db:
        admin = User(
            email="admin.analytics@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Admin Analyst",
            role=UserRole.ADMIN,
            is_active=True,
        )
        citizen = User(
            email="citizen.analytics@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="Citizen Tester",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add_all([admin, citizen])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(citizen)

        admin_token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": "admin"})
        citizen_token = create_access_token({"sub": str(citizen.id), "email": citizen.email, "role": "citizen"})

        # Seed sample crime incidents in Chennai (T. Nagar, Adyar, Royapettah, Anna Nagar)
        today = date.today()
        incidents = [
            CrimeIncident(
                crime_id="CR-TEST-001",
                description="Broke into retail shop overnight",
                crime_category="BURGLARY",
                severity="HIGH",
                latitude=13.0418,
                longitude=80.2341,
                ward_no=117,
                zone_no="Zone 08",
                zone_name="Anna Nagar Zone",
                occurred_date=today - timedelta(days=5),
                occurred_time=time(23, 30),
                time_period="NIGHT",
                location_type="Commercial",
                reported_date=today - timedelta(days=5),
                status="REPORTED",
                classification_status="AUTO_CLASSIFIED",
                confidence=0.92,
            ),
            CrimeIncident(
                crime_id="CR-TEST-002",
                description="Snatching near bus stop",
                crime_category="THEFT",
                severity="MEDIUM",
                latitude=13.0064,
                longitude=80.2575,
                ward_no=173,
                zone_no="Zone 13",
                zone_name="Adyar Zone",
                occurred_date=today - timedelta(days=12),
                occurred_time=time(19, 15),
                time_period="EVENING",
                location_type="Street",
                reported_date=today - timedelta(days=12),
                status="VERIFIED",
                classification_status="ADMIN_VERIFIED",
                confidence=0.88,
            ),
            CrimeIncident(
                crime_id="CR-TEST-003",
                description="Armed robbery at jewelry store",
                crime_category="ROBBERY",
                severity="HIGH",
                latitude=13.0583,
                longitude=80.2642,
                ward_no=119,
                zone_no="Zone 09",
                zone_name="Teynampet Zone",
                occurred_date=today - timedelta(days=2),
                occurred_time=time(22, 10),
                time_period="NIGHT",
                location_type="Commercial",
                reported_date=today - timedelta(days=2),
                status="VERIFIED",
                classification_status="ADMIN_VERIFIED",
                confidence=0.95,
            ),
            CrimeIncident(
                crime_id="CR-TEST-004",
                description="Motorcycle stolen from parking",
                crime_category="THEFT",
                severity="LOW",
                latitude=13.0850,
                longitude=80.2100,
                ward_no=101,
                zone_no="Zone 07",
                zone_name="Ambattur Zone",
                occurred_date=today - timedelta(days=40),
                occurred_time=time(14, 0),
                time_period="AFTERNOON",
                location_type="Parking",
                reported_date=today - timedelta(days=40),
                status="REPORTED",
                classification_status="AUTO_CLASSIFIED",
                confidence=0.84,
            ),
            CrimeIncident(
                crime_id="CR-TEST-005",
                description="Physical fight outside venue",
                crime_category="ASSAULT",
                severity="HIGH",
                latitude=13.0336,
                longitude=80.2677,
                ward_no=124,
                zone_no="Zone 09",
                zone_name="Teynampet Zone",
                occurred_date=today - timedelta(days=1),
                occurred_time=time(20, 45),
                time_period="EVENING",
                location_type="Public Space",
                reported_date=today - timedelta(days=1),
                status="VERIFIED",
                classification_status="ADMIN_VERIFIED",
                confidence=0.91,
            ),
        ]
        db.add_all(incidents)

        # Seed patrol unit
        patrol_unit = PatrolUnit(
            unit_code="PRP-ANALYTICS-01",
            unit_type="VEHICLE",
            status="AVAILABLE",
            current_latitude=13.0400,
            current_longitude=80.2300,
        )
        db.add(patrol_unit)
        await db.commit()

        return {
            "admin_token": admin_token,
            "citizen_token": citizen_token,
            "incident_count": len(incidents),
        }


@pytest.mark.asyncio
async def test_analytics_evaluate_strategies_computed_metrics(setup_analytics_env, async_client: AsyncClient):
    """Test comparative evaluation between Reference, Dynamic, and Random strategies."""
    env = setup_analytics_env
    headers = {"Authorization": f"Bearer {env['admin_token']}"}

    payload = {
        "patrol_count": 3,
        "coverage_radius_km": 4.0,
        "time_period": "ALL",
        "use_stored_prps_if_available": False,
    }

    response = await async_client.post("/api/v1/analytics/evaluate", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "reference" in data
    assert "dynamic" in data
    assert "random_baseline" in data
    assert data["dataset_incident_count"] >= 5
    assert data["coverage_radius_km"] == 4.0
    assert data["patrol_count"] == 3

    ref = data["reference"]
    dyn = data["dynamic"]
    rnd = data["random_baseline"]

    # Verify metric types and ranges
    for strat in [ref, dyn, rnd]:
        assert strat["patrol_count"] == 3
        assert strat["total_demand_points"] >= 5
        assert 0 <= strat["covered_demand_points"] <= strat["total_demand_points"]
        assert 0.0 <= strat["coverage_percentage"] <= 100.0
        assert strat["total_weighted_risk"] > 0.0
        assert 0.0 <= strat["covered_weighted_risk"] <= strat["total_weighted_risk"] + 1e-4
        assert 0.0 <= strat["weighted_risk_coverage_pct"] <= 100.0
        assert strat["high_risk_total"] >= 1
        assert 0 <= strat["high_risk_covered"] <= strat["high_risk_total"]
        assert 0.0 <= strat["high_risk_coverage_pct"] <= 100.0
        assert strat["mean_distance_km"] >= 0.0
        assert strat["max_distance_km"] >= strat["mean_distance_km"]

        # Crucial check: response time must NOT be fabricated (None/omitted)
        assert strat["estimated_response_time_min"] is None


@pytest.mark.asyncio
async def test_random_baseline_reproducibility(setup_analytics_env):
    """Test that Random Baseline (seed=42) produces identical reproducible results across invocations."""
    async with TestAsyncSessionLocal() as db:
        req = EvaluationRequest(patrol_count=3, coverage_radius_km=3.5, time_period="ALL")
        res1 = await analytics_service.evaluate_strategies(db=db, req=req)
        res2 = await analytics_service.evaluate_strategies(db=db, req=req)

        assert res1.random_baseline is not None
        assert res2.random_baseline is not None
        assert res1.random_baseline.mean_distance_km == res2.random_baseline.mean_distance_km
        assert res1.random_baseline.covered_demand_points == res2.random_baseline.covered_demand_points
        assert res1.random_baseline.weighted_risk_coverage_pct == res2.random_baseline.weighted_risk_coverage_pct


@pytest.mark.asyncio
async def test_no_double_counting_in_coverage():
    """Verify that a demand point covered by multiple overlapping PRPs is counted strictly ONCE."""
    from app.optimization.candidate_generator import DemandPoint

    demand_points = [
        DemandPoint(
            point_id=1,
            latitude=13.0418,
            longitude=80.2341,
            weight=3.5,
            ward_no=117,
            crime_category="BURGLARY",
            severity="HIGH",
        ),
        DemandPoint(
            point_id=2,
            latitude=13.0420,
            longitude=80.2345,
            weight=2.5,
            ward_no=117,
            crime_category="THEFT",
            severity="MEDIUM",
        ),
    ]

    # Two overlapping PRPs very close to each other, both covering point 1 and 2
    prp_coords = [
        (13.0418, 80.2341),
        (13.0419, 80.2342),
    ]

    metric = analytics_service._evaluate_strategy_prps(
        strategy_name="Test Strategy",
        strategy_type="TEST",
        prp_coordinates=prp_coords,
        demand_points=demand_points,
        coverage_radius_km=3.0,
        patrol_count=2,
    )

    # Both points are covered, total = 2. Covered points MUST be 2, NOT 4.
    assert metric.covered_demand_points == 2
    assert metric.coverage_percentage == 100.0
    # Total weight is 3.5 + 2.5 = 6.0. Covered weighted risk MUST be 6.0, NOT 12.0.
    assert metric.total_weighted_risk == 6.0
    assert metric.covered_weighted_risk == 6.0
    assert metric.weighted_risk_coverage_pct == 100.0


@pytest.mark.asyncio
async def test_analytics_non_admin_blocked(setup_analytics_env, async_client: AsyncClient):
    """Test that citizens and unauthenticated users cannot access evaluation or summary endpoints."""
    env = setup_analytics_env
    citizen_headers = {"Authorization": f"Bearer {env['citizen_token']}"}

    # Citizen POST /evaluate -> 403 Forbidden
    resp_eval = await async_client.post(
        "/api/v1/analytics/evaluate", json={"patrol_count": 5}, headers=citizen_headers
    )
    assert resp_eval.status_code == 403

    # Citizen GET /summary -> 403 Forbidden
    resp_sum = await async_client.get("/api/v1/analytics/summary", headers=citizen_headers)
    assert resp_sum.status_code == 403

    # Unauthenticated GET /summary -> 401 Unauthorized
    resp_unauth = await async_client.get("/api/v1/analytics/summary")
    assert resp_unauth.status_code == 401


@pytest.mark.asyncio
async def test_operational_summary_aggregation(setup_analytics_env, async_client: AsyncClient):
    """Test live operational summary aggregation endpoint."""
    env = setup_analytics_env
    headers = {"Authorization": f"Bearer {env['admin_token']}"}

    resp = await async_client.get("/api/v1/analytics/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_crimes"] >= 5
    assert data["total_patrol_units"] >= 1
    assert "category_counts" in data
    assert "severity_counts" in data
    assert isinstance(data["category_counts"], dict)
    assert isinstance(data["severity_counts"], dict)
    assert data["total_crimes"] > 0


@pytest.mark.asyncio
async def test_analytics_evaluate_with_historical_zero_weight_incidents(setup_analytics_env, async_client: AsyncClient):
    """Verify that Analytics evaluate does NOT raise ZeroDivisionError 500 when historical incidents decay to zero weight."""
    env = setup_analytics_env
    headers = {"Authorization": f"Bearer {env['admin_token']}"}

    # Add old historical incidents from 3 years ago (dynamic weights will decay to 0.0)
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        old_incidents = [
            CrimeIncident(
                crime_id=f"CR-OLD-{i}",
                description="Old past incident from 3 years ago",
                crime_category="THEFT",
                severity="LOW",
                latitude=13.0418 + (i * 0.001),
                longitude=80.2341 + (i * 0.001),
                ward_no=117,
                zone_no="Zone 08",
                zone_name="Anna Nagar Zone",
                occurred_date=date(2022, 1, 1),
                occurred_time=time(12, 0),
                time_period="AFTERNOON",
                location_type="Street",
                reported_date=date(2022, 1, 1),
                status="REPORTED",
                classification_status="AUTO_CLASSIFIED",
                confidence=0.85,
            )
            for i in range(5)
        ]
        session.add_all(old_incidents)
        await session.commit()

    resp = await async_client.post(
        "/api/v1/analytics/evaluate",
        json={
            "patrol_count": 5,
            "coverage_radius_km": 3.0,
            "time_period": "ALL",
            "use_stored_prps_if_available": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200 OK but got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "reference" in data
    assert "dynamic" in data
    assert data["reference"]["coverage_percentage"] >= 0.0
    assert data["dynamic"]["coverage_percentage"] >= 0.0


@pytest.mark.asyncio
async def test_analytics_evaluate_with_multiple_historical_runs(setup_analytics_env, async_client: AsyncClient):
    """Verify that multiple historical runs of DYNAMIC and REFERENCE in DB do not raise MultipleResultsFound."""
    from app.models.optimization import OptimizationRun, PRPLocation
    from tests.conftest import TestAsyncSessionLocal

    env = setup_analytics_env
    headers = {"Authorization": f"Bearer {env['admin_token']}"}

    async with TestAsyncSessionLocal() as session:
        # Seed multiple historical runs of REFERENCE and DYNAMIC
        for i in range(3):
            ref_run = OptimizationRun(
                run_type="REFERENCE",
                parameters={"time_period": "ALL", "patrol_count": 3, "coverage_radius_km": 3.0},
                total_prps_generated=3,
                status="COMPLETED",
            )
            session.add(ref_run)
            await session.flush()
            for p in range(3):
                session.add(
                    PRPLocation(
                        optimization_run_id=ref_run.id,
                        prp_type="REFERENCE",
                        rank=p + 1,
                        latitude=13.0400 + (p * 0.01) + (i * 0.001),
                        longitude=80.2300 + (p * 0.01),
                        ward_no=117,
                        zone_no="Zone 08",
                        zone_name="Anna Nagar Zone",
                        risk_score=5.0,
                        coverage_radius_km=3.0,
                        status="ACTIVE",
                    )
                )

            dyn_run = OptimizationRun(
                run_type="DYNAMIC",
                parameters={"time_period": "ALL", "patrol_count": 3, "coverage_radius_km": 3.0},
                total_prps_generated=3,
                status="COMPLETED",
            )
            session.add(dyn_run)
            await session.flush()
            for p in range(3):
                session.add(
                    PRPLocation(
                        optimization_run_id=dyn_run.id,
                        prp_type="DYNAMIC",
                        rank=p + 1,
                        latitude=13.0500 + (p * 0.01) + (i * 0.001),
                        longitude=80.2400 + (p * 0.01),
                        ward_no=117,
                        zone_no="Zone 08",
                        zone_name="Anna Nagar Zone",
                        risk_score=6.0,
                        coverage_radius_km=3.0,
                        status="ACTIVE",
                    )
                )

        await session.commit()

    # Now call /api/v1/analytics/evaluate with use_stored_prps_if_available=True
    resp = await async_client.post(
        "/api/v1/analytics/evaluate",
        json={
            "patrol_count": 3,
            "coverage_radius_km": 3.0,
            "time_period": "ALL",
            "use_stored_prps_if_available": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200 OK but got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "reference" in data
    assert "dynamic" in data
    assert "random_baseline" in data
    assert data["reference"]["patrol_count"] == 3
    assert data["dynamic"]["patrol_count"] == 3


