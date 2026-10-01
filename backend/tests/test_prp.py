"""SafeZone PRP Optimization and Deployment Test Suite.

Verifies:
- Zero crime demand points (safe empty handling)
- Zero patrol count requested
- Single patrol unit optimization (K=1)
- Multiple patrol units optimization (K > 1)
- Overlapping coverage (Unique weighted risk coverage, no double counting)
- Insufficient candidates handling (|J| < K)
- Configurable coverage radius (3.0 km vs 5.0 km)
- REFERENCE mode vs DYNAMIC mode optimization runs
- PRP status transition workflow (RECOMMENDED -> APPROVED -> ACTIVE)
- Privacy enforcement: Exact PRP coordinates strictly blocked for Citizens (403 Forbidden).
"""

import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.models.crime import CrimeIncident
from app.models.optimization import OptimizationRun, PRPLocation
from app.core.security import get_password_hash, create_access_token
from app.optimization.candidate_generator import (
    candidate_generator,
    CandidateLocation,
    DemandPoint,
)
from app.optimization.prp_optimizer import prp_optimizer, OptimizationResult


@pytest_asyncio.fixture
async def admin_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        admin = User(
            email="admin_prp@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="PRP Admin Officer",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def police_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        police = User(
            email="police_prp@safezone.org",
            hashed_password=get_password_hash("PolicePass123!"),
            full_name="Police Patrol Officer",
            role=UserRole.POLICE,
            is_active=True,
        )
        session.add(police)
        await session.commit()
        await session.refresh(police)

    token = create_access_token({"sub": str(police.id), "email": police.email, "role": "POLICE"})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def citizen_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        citizen = User(
            email="citizen_prp@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="Citizen User",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        session.add(citizen)
        await session.commit()
        await session.refresh(citizen)

    token = create_access_token({"sub": str(citizen.id), "email": citizen.email, "role": "CITIZEN"})
    return {"Authorization": f"Bearer {token}"}


# ==========================================
# 1. OPTIMIZER MATHEMATICAL CORE TESTS
# ==========================================

def test_optimizer_zero_crimes():
    """Verify optimizer handles zero crime demand points safely."""
    res = prp_optimizer.optimize(
        candidates=[],
        demand_points=[],
        patrol_count=5,
        coverage_radius_km=3.0,
    )
    assert res.status == "NO_DATA"
    assert len(res.selected_prps) == 0
    assert res.covered_demand_points == 0
    assert res.coverage_percentage == 0.0


def test_optimizer_zero_patrol_count():
    """Verify optimizer handles requested patrol_count=0."""
    demand = [
        DemandPoint(point_id=1, latitude=13.08, longitude=80.27, weight=3.0),
        DemandPoint(point_id=2, latitude=13.09, longitude=80.28, weight=2.0),
    ]
    candidates = [
        CandidateLocation(candidate_id=1, latitude=13.08, longitude=80.27, ward_no=1, zone_no="I", zone_name="A")
    ]
    res = prp_optimizer.optimize(
        candidates=candidates,
        demand_points=demand,
        patrol_count=0,
    )
    assert res.status == "OPTIMAL"
    assert len(res.selected_prps) == 0
    assert res.covered_demand_points == 0
    assert res.coverage_percentage == 0.0


def test_optimizer_single_patrol():
    """Verify K=1 selects the single best candidate with maximal covered weight."""
    # Two clusters: Cluster A (weight 10), Cluster B (weight 3)
    demand = [
        # Cluster A around (13.08, 80.27)
        DemandPoint(point_id=1, latitude=13.080, longitude=80.270, weight=5.0),
        DemandPoint(point_id=2, latitude=13.081, longitude=80.271, weight=5.0),
        # Cluster B around (13.20, 80.20)
        DemandPoint(point_id=3, latitude=13.200, longitude=80.200, weight=3.0),
    ]
    candidates = [
        CandidateLocation(candidate_id=1, latitude=13.080, longitude=80.270, ward_no=100, zone_no="VIII", zone_name="ZoneA"),
        CandidateLocation(candidate_id=2, latitude=13.200, longitude=80.200, ward_no=10, zone_no="I", zone_name="ZoneB"),
    ]

    res = prp_optimizer.optimize(
        candidates=candidates,
        demand_points=demand,
        patrol_count=1,
        coverage_radius_km=2.0,
    )
    assert res.status == "OPTIMAL"
    assert len(res.selected_prps) == 1
    # Must select Candidate 1 because it covers weight 10 vs weight 3
    assert res.selected_prps[0].candidate_id == 1
    assert res.covered_demand_points == 2
    assert res.covered_weighted_risk == 10.0


def test_optimizer_overlapping_coverage_no_double_counting():
    """Verify unique coverage objective prevents double counting overlapping demand points."""
    # Point 2 is covered by both Candidate 1 and Candidate 2
    demand = [
        DemandPoint(point_id=1, latitude=13.080, longitude=80.270, weight=4.0),
        DemandPoint(point_id=2, latitude=13.085, longitude=80.275, weight=6.0),  # Overlap point
        DemandPoint(point_id=3, latitude=13.090, longitude=80.280, weight=4.0),
    ]
    candidates = [
        CandidateLocation(candidate_id=1, latitude=13.080, longitude=80.270, ward_no=1, zone_no="I", zone_name="Z1"),
        CandidateLocation(candidate_id=2, latitude=13.090, longitude=80.280, ward_no=2, zone_no="I", zone_name="Z2"),
    ]

    res = prp_optimizer.optimize(
        candidates=candidates,
        demand_points=demand,
        patrol_count=2,
        coverage_radius_km=2.0,
    )
    assert res.status == "OPTIMAL"
    assert len(res.selected_prps) == 2
    # Total unique covered weight must be 4 + 6 + 4 = 14 (NOT 20 from double counting point 2)
    assert res.total_weighted_risk == 14.0
    assert res.covered_weighted_risk == 14.0
    assert res.coverage_percentage == 100.0


def test_optimizer_insufficient_candidates():
    """Verify optimizer handles case when candidate count < patrol_count."""
    demand = [
        DemandPoint(point_id=1, latitude=13.08, longitude=80.27, weight=2.0),
    ]
    candidates = [
        CandidateLocation(candidate_id=1, latitude=13.08, longitude=80.27, ward_no=1, zone_no="I", zone_name="A"),
    ]
    # Request 10 patrols when only 1 candidate exists
    res = prp_optimizer.optimize(
        candidates=candidates,
        demand_points=demand,
        patrol_count=10,
    )
    assert res.status == "OPTIMAL"
    assert len(res.selected_prps) == 1


def test_configurable_coverage_radius():
    """Verify larger coverage radius (5 km vs 2 km) captures more distant demand points."""
    # Point at ~3.5 km distance from candidate
    candidate = CandidateLocation(candidate_id=1, latitude=13.080, longitude=80.270, ward_no=1, zone_no="I", zone_name="A")
    demand = [
        DemandPoint(point_id=1, latitude=13.080, longitude=80.300, weight=5.0),  # ~3.2 km away
    ]

    # Radius 2.0 km -> 0% coverage
    res_small = prp_optimizer.optimize(
        candidates=[candidate],
        demand_points=demand,
        patrol_count=1,
        coverage_radius_km=2.0,
    )
    assert res_small.covered_demand_points == 0

    # Radius 5.0 km -> 100% coverage
    res_large = prp_optimizer.optimize(
        candidates=[candidate],
        demand_points=demand,
        patrol_count=1,
        coverage_radius_km=5.0,
    )
    assert res_large.covered_demand_points == 1
    assert res_large.coverage_percentage == 100.0


def test_candidate_generator_positive_weight_group():
    """Verify CandidateGenerator computes weighted centroid correctly for positive-weight incident clusters."""
    demand = [
        DemandPoint(point_id=1, latitude=13.080, longitude=80.270, weight=1.0, ward_no=119),
        DemandPoint(point_id=2, latitude=13.082, longitude=80.272, weight=3.0, ward_no=119),
    ]
    candidates = candidate_generator.generate_candidates(demand_points=demand, target_ward_numbers=[119], min_separation_km=0.0)
    assert len(candidates) > 0
    # Hotspot center should be weighted towards point 2
    # lat = (13.080*1.0 + 13.082*3.0)/4.0 = 13.0815
    # lon = (80.270*1.0 + 80.272*3.0)/4.0 = 80.2715
    hotspots = [c for c in candidates if c.source_type == "HOTSPOT_CENTER"]
    assert len(hotspots) >= 1
    assert abs(hotspots[0].latitude - 13.0815) < 0.001
    assert abs(hotspots[0].longitude - 80.2715) < 0.001


def test_candidate_generator_zero_total_weight_group():
    """Verify CandidateGenerator safely uses unweighted geographic centroid without ZeroDivisionError when total_weight=0."""
    demand = [
        DemandPoint(point_id=1, latitude=13.080, longitude=80.270, weight=0.0, ward_no=119),
        DemandPoint(point_id=2, latitude=13.082, longitude=80.272, weight=0.0, ward_no=119),
    ]
    candidates = candidate_generator.generate_candidates(demand_points=demand, target_ward_numbers=[119], min_separation_km=0.0)
    assert len(candidates) > 0
    # Unweighted centroid: lat = (13.080 + 13.082)/2 = 13.081, lon = (80.270 + 80.272)/2 = 80.271
    hotspots = [c for c in candidates if c.source_type == "HOTSPOT_CENTER"]
    assert len(hotspots) >= 1
    assert abs(hotspots[0].latitude - 13.081) < 0.001
    assert abs(hotspots[0].longitude - 80.271) < 0.001


def test_candidate_generator_empty_and_invalid_group():
    """Verify CandidateGenerator safely handles empty demand points list or single points."""
    # 1. Empty demand points list
    cand_empty = candidate_generator.generate_candidates(demand_points=[])
    assert len(cand_empty) > 0  # Ward centroids are still returned as base positioning anchors
    assert all(c.source_type == "WARD_CENTROID" for c in cand_empty)

    # 2. Single demand point (less than 2 in a bin -> no hotspot cluster created, handled safely)
    single_demand = [
        DemandPoint(point_id=1, latitude=13.08, longitude=80.27, weight=1.0),
    ]
    cand_single = candidate_generator.generate_candidates(demand_points=single_demand)
    assert len(cand_single) > 0



# ==========================================
# 2. FASTAPI API INTEGRATION & PRIVACY TESTS
# ==========================================

@pytest.mark.asyncio
async def test_privacy_citizen_blocked_from_prp(async_client: AsyncClient, citizen_auth_header: dict):
    """Verify CITIZEN role is blocked with 403 Forbidden from accessing PRP endpoints."""
    # 1. Citizen cannot optimize
    res1 = await async_client.post(
        "/api/v1/prp/optimize",
        json={"mode": "DYNAMIC", "patrol_count": 5},
        headers=citizen_auth_header,
    )
    assert res1.status_code == 403

    # 2. Citizen cannot list active PRPs
    res2 = await async_client.get("/api/v1/prp/active", headers=citizen_auth_header)
    assert res2.status_code == 403

    # 3. Citizen cannot list runs
    res3 = await async_client.get("/api/v1/prp/runs", headers=citizen_auth_header)
    assert res3.status_code == 403


@pytest.mark.asyncio
async def test_admin_prp_optimization_preview(async_client: AsyncClient, admin_auth_header: dict):
    """Verify admin can preview optimization without persisting to DB."""
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as session:
        c1 = CrimeIncident(
            crime_id="CR-PRP-001",
            description="Motorcycle theft.",
            crime_category="THEFT",
            severity="MEDIUM",
            latitude=13.0827,
            longitude=80.2707,
            ward_no=119,
            zone_no="IX",
            zone_name="TEYNAMPET",
            occurred_date=date.today(),
            occurred_time=time(14, 0),
            time_period="AFTERNOON",
            location_type="ROAD",
            reported_date=date.today(),
            status="REPORTED",
            classification_status="AUTO_CLASSIFIED",
        )
        session.add(c1)
        await session.commit()

    payload = {
        "mode": "DYNAMIC",
        "patrol_count": 3,
        "coverage_radius_km": 3.0,
        "time_period": "ALL",
        "save_run": False,
    }
    response = await async_client.post("/api/v1/prp/optimize", json=payload, headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["run_type"] == "DYNAMIC"
    assert data["status"] == "OPTIMAL"
    assert len(data["selected_prps"]) >= 1
    assert data["run_id"] is None  # Not saved


@pytest.mark.asyncio
async def test_admin_prp_run_save_and_status_lifecycle(
    async_client: AsyncClient,
    admin_auth_header: dict,
    police_auth_header: dict,
):
    """Verify complete lifecycle: Run -> Save -> Update Status -> Active Listing for Police."""
    from tests.conftest import TestAsyncSessionLocal

    # 1. Create incident
    async with TestAsyncSessionLocal() as session:
        c1 = CrimeIncident(
            crime_id="CR-PRP-002",
            description="Commercial burglary.",
            crime_category="BURGLARY",
            severity="HIGH",
            latitude=13.0827,
            longitude=80.2707,
            ward_no=119,
            zone_no="IX",
            zone_name="TEYNAMPET",
            occurred_date=date.today(),
            occurred_time=time(2, 0),
            time_period="NIGHT",
            location_type="COMMERCIAL_AREA",
            reported_date=date.today(),
            status="REPORTED",
            classification_status="AUTO_CLASSIFIED",
        )
        session.add(c1)
        await session.commit()

    # 2. Admin creates optimization run with persistence (POST /api/v1/prp/runs)
    payload = {
        "mode": "REFERENCE",
        "patrol_count": 2,
        "coverage_radius_km": 3.0,
        "time_period": "ALL",
    }
    create_res = await async_client.post("/api/v1/prp/runs", json=payload, headers=admin_auth_header)
    assert create_res.status_code == 201
    run_data = create_res.json()
    run_id = run_data["run_id"]
    assert run_id is not None
    assert len(run_data["selected_prps"]) >= 1

    first_prp_id = run_data["selected_prps"][0]["id"]
    assert first_prp_id is not None
    assert run_data["selected_prps"][0]["status"] == "RECOMMENDED"

    # 3. Admin updates status to ACTIVE (POST /api/v1/prp/{prp_id}/status)
    status_res = await async_client.post(
        f"/api/v1/prp/{first_prp_id}/status",
        json={"status": "ACTIVE"},
        headers=admin_auth_header,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "ACTIVE"

    # 4. Police Officer lists active PRPs (GET /api/v1/prp/active)
    police_active_res = await async_client.get("/api/v1/prp/active", headers=police_auth_header)
    assert police_active_res.status_code == 200
    active_prps = police_active_res.json()
    assert len(active_prps) >= 1
    assert any(p["id"] == first_prp_id for p in active_prps)

    # 5. Police Officer inspects the run details (GET /api/v1/prp/runs/{run_id})
    run_details_res = await async_client.get(f"/api/v1/prp/runs/{run_id}", headers=police_auth_header)
    assert run_details_res.status_code == 200
    assert run_details_res.json()["id"] == run_id
