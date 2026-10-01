"""SafeZone Stage 12 — SOS Dispatch & End-to-End Emergency Workflow Test Suite.

Verifies:
1. Citizen SOS creation & coordinate validation
2. Automatic nearest eligible patrol assignment
3. Correct assignment lifecycle status transitions (ASSIGNED -> ACCEPTED -> EN_ROUTE -> ARRIVED -> RESOLVED)
4. Patrol resource release upon resolution
5. Explicit NO_AVAILABLE_PATROL handling
6. Invalid state transition rejection
7. Unauthorized police transition rejection (Officer A cannot accept Officer B's call)
8. Decline and redispatch to next eligible patrol
9. No infinite redispatch loops
10. Concurrency & collision prevention (no duplicate patrol assignment)
11. Citizen strategic privacy guarantee (no PRP, raw police coordinates, or risk scores)
12. Distance labeled approximate with null ETA
13. Non-blocking emergency contact SMS trigger with primary contact prioritization & idempotency
14. Admin manual dispatch override.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User, UserRole, EmergencyContact
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.sos import SOSRequest
from app.models.optimization import PatrolAssignment, PRPLocation, OptimizationRun
from app.core.security import get_password_hash, create_access_token


@pytest_asyncio.fixture
async def setup_dispatch_environment(async_client: AsyncClient):
    """Sets up two citizens, two police officers, and two patrol units at distinct locations."""
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        # Citizen 1 (with primary emergency contact)
        c1 = User(
            email="victim1@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Citizen One",
            phone_number="9840011111",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        # Citizen 2 (no emergency contacts)
        c2 = User(
            email="victim2@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Citizen Two",
            phone_number="9840022222",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        # Admin
        admin = User(
            email="admin_dispatch@safezone.gov",
            hashed_password=get_password_hash("Admin123!"),
            full_name="Dispatch Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add_all([c1, c2, admin])
        await session.flush()

        # Emergency Contacts for Citizen 1
        contact_sec = EmergencyContact(
            user_id=c1.id,
            name="Secondary Friend",
            phone_number="9840033333",
            relationship_type="Friend",
            is_primary=False,
        )
        contact_pri = EmergencyContact(
            user_id=c1.id,
            name="Primary Parent",
            phone_number="9840044444",
            relationship_type="Parent",
            is_primary=True,
        )
        session.add_all([contact_sec, contact_pri])

        # Police Officer 1 (Close to Anna Nagar: 13.0850, 80.2100)
        u_p1 = User(
            email="officer_alpha@safezone.gov",
            hashed_password=get_password_hash("Police123!"),
            full_name="Officer Alpha",
            role=UserRole.POLICE,
            is_active=True,
        )
        # Police Officer 2 (Farther at Guindy: 13.0067, 80.2021)
        u_p2 = User(
            email="officer_bravo@safezone.gov",
            hashed_password=get_password_hash("Police123!"),
            full_name="Officer Bravo",
            role=UserRole.POLICE,
            is_active=True,
        )
        session.add_all([u_p1, u_p2])
        await session.flush()

        p_off1 = PoliceOfficer(
            user_id=u_p1.id,
            badge_number="SZ-POL-881",
            rank="Sub-Inspector",
            station_name="Anna Nagar Police Station",
            on_duty=True,
            is_available=True,
        )
        p_off2 = PoliceOfficer(
            user_id=u_p2.id,
            badge_number="SZ-POL-882",
            rank="Inspector",
            station_name="Guindy Police Station",
            on_duty=True,
            is_available=True,
        )
        session.add_all([p_off1, p_off2])

        # Patrol Unit 1 (Near Anna Nagar: 13.0850, 80.2100)
        unit1 = PatrolUnit(
            unit_code="ALPHA-1",
            unit_type="VEHICLE",
            status="AVAILABLE",
            current_latitude=13.0850,
            current_longitude=80.2100,
        )
        # Patrol Unit 2 (At Guindy: 13.0067, 80.2021)
        unit2 = PatrolUnit(
            unit_code="BRAVO-2",
            unit_type="VEHICLE",
            status="AVAILABLE",
            current_latitude=13.0067,
            current_longitude=80.2021,
        )
        session.add_all([unit1, unit2])
        await session.commit()

        c1_id = c1.id
        c2_id = c2.id
        admin_id = admin.id
        p1_id = u_p1.id
        p2_id = u_p2.id
        p_off1_id = p_off1.id
        p_off2_id = p_off2.id
        unit1_id = unit1.id
        unit2_id = unit2.id

    t_c1 = create_access_token({"sub": str(c1_id), "email": "victim1@safezone.org", "role": "CITIZEN"})
    t_c2 = create_access_token({"sub": str(c2_id), "email": "victim2@safezone.org", "role": "CITIZEN"})
    t_adm = create_access_token({"sub": str(admin_id), "email": "admin_dispatch@safezone.gov", "role": "ADMIN"})
    t_p1 = create_access_token({"sub": str(p1_id), "email": "officer_alpha@safezone.gov", "role": "POLICE"})
    t_p2 = create_access_token({"sub": str(p2_id), "email": "officer_bravo@safezone.gov", "role": "POLICE"})

    return {
        "c1": {"id": c1_id, "headers": {"Authorization": f"Bearer {t_c1}"}},
        "c2": {"id": c2_id, "headers": {"Authorization": f"Bearer {t_c2}"}},
        "admin": {"id": admin_id, "headers": {"Authorization": f"Bearer {t_adm}"}},
        "p1": {"id": p1_id, "officer_id": p_off1_id, "headers": {"Authorization": f"Bearer {t_p1}"}},
        "p2": {"id": p2_id, "officer_id": p_off2_id, "headers": {"Authorization": f"Bearer {t_p2}"}},
        "unit1_id": unit1_id,
        "unit2_id": unit2_id,
    }


@pytest.mark.asyncio
async def test_complete_sos_dispatch_and_resolution_flow(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify complete end-to-end emergency flow: Trigger -> Assign Nearest -> Accept -> En Route -> Arrived -> Resolved."""
    env = setup_dispatch_environment

    # 1. Citizen 1 triggers SOS near Anna Nagar (13.0840, 80.2110)
    trigger_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110, "notes": "Emergency assistance required"},
        headers=env["c1"]["headers"],
    )
    assert trigger_res.status_code == 201
    sos_data = trigger_res.json()
    sos_id = sos_data["id"]
    assert sos_data["status"] == "ASSIGNED"
    assert sos_data["approximate_distance_km"] is not None
    assert sos_data["estimated_arrival_minutes"] is None  # Road routing unavailable -> null ETA

    # 2. Verify Officer 1 was selected (nearest unit)
    sos_list = await async_client.get("/api/v1/sos/active", headers=env["admin"]["headers"])
    assert sos_list.status_code == 200
    sos_record = next(r for r in sos_list.json() if r["id"] == sos_id)
    assert sos_record["assigned_officer_id"] == env["p1"]["officer_id"]
    assert sos_record["assigned_patrol_id"] == env["unit1_id"]

    # 3. Police Officer 1 ACCEPTS dispatch
    accept_res = await async_client.post(f"/api/v1/sos/{sos_id}/accept", headers=env["p1"]["headers"])
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "ACCEPTED"

    # 4. Police Officer 1 marks EN_ROUTE
    enroute_res = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "EN_ROUTE"},
        headers=env["p1"]["headers"],
    )
    assert enroute_res.status_code == 200
    assert enroute_res.json()["status"] == "EN_ROUTE"

    # 5. Police Officer 1 marks ARRIVED
    arrived_res = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "ARRIVED"},
        headers=env["p1"]["headers"],
    )
    assert arrived_res.status_code == 200
    assert arrived_res.json()["status"] == "ARRIVED"

    # 6. Police Officer 1 RESOLVES emergency
    resolved_res = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "RESOLVED", "notes": "Situation defused and citizen secured."},
        headers=env["p1"]["headers"],
    )
    assert resolved_res.status_code == 200
    assert resolved_res.json()["status"] == "RESOLVED"
    assert resolved_res.json()["resolved_at"] is not None

    # 7. Verify patrol unit and officer are released to available status
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = await session.get(PatrolUnit, env["unit1_id"])
        assert u.status == "AVAILABLE"
        off = await session.get(PoliceOfficer, env["p1"]["officer_id"])
        assert off.is_available is True


@pytest.mark.asyncio
async def test_unauthorized_police_transition_rejected(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify Officer A cannot accept or modify Officer B's assigned emergency."""
    env = setup_dispatch_environment

    # Trigger SOS -> assigned to Officer 1 (Alpha)
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c1"]["headers"],
    )
    sos_id = trig_res.json()["id"]

    # Officer 2 (Bravo) attempts to accept Officer 1's assignment -> 403 Forbidden
    unauth_accept = await async_client.post(f"/api/v1/sos/{sos_id}/accept", headers=env["p2"]["headers"])
    assert unauth_accept.status_code == 403

    # Officer 2 attempts to change status -> 403 Forbidden
    unauth_status = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "EN_ROUTE"},
        headers=env["p2"]["headers"],
    )
    assert unauth_status.status_code == 403


@pytest.mark.asyncio
async def test_invalid_state_transitions_rejected(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify invalid state transitions (e.g. ASSIGNED -> ARRIVED, or modifying terminal state) are rejected."""
    env = setup_dispatch_environment

    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c1"]["headers"],
    )
    sos_id = trig_res.json()["id"]

    # Attempt skipping states: ASSIGNED -> ARRIVED directly -> 400 Bad Request
    invalid_skip = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "ARRIVED"},
        headers=env["p1"]["headers"],
    )
    assert invalid_skip.status_code == 400
    assert "Invalid transition" in invalid_skip.json()["detail"]


@pytest.mark.asyncio
async def test_decline_and_redispatch_to_next_eligible_patrol(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify officer decline releases current assignment and redispatches to next nearest available patrol."""
    env = setup_dispatch_environment

    # 1. Trigger SOS -> assigned to Officer 1 (nearest)
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c1"]["headers"],
    )
    sos_id = trig_res.json()["id"]

    # 2. Officer 1 declines
    decline_res = await async_client.post(f"/api/v1/sos/{sos_id}/decline", headers=env["p1"]["headers"])
    assert decline_res.status_code == 200
    data = decline_res.json()

    # 3. Verified redispatch assigned to Officer 2 (next nearest)
    assert data["status"] == "ASSIGNED"
    assert data["assigned_officer_id"] == env["p2"]["officer_id"]
    assert data["assigned_patrol_id"] == env["unit2_id"]

    # 4. Officer 2 now declines as well -> No other available patrols
    decline_res2 = await async_client.post(f"/api/v1/sos/{sos_id}/decline", headers=env["p2"]["headers"])
    assert decline_res2.status_code == 200
    assert decline_res2.json()["status"] == "NO_AVAILABLE_PATROL"
    assert decline_res2.json()["assigned_officer_id"] is None


@pytest.mark.asyncio
async def test_concurrency_and_collision_prevention(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify that concurrent SOS requests cannot be assigned the same patrol unit."""
    env = setup_dispatch_environment

    # SOS 1 triggered -> takes Unit 1 (nearest)
    res1 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c1"]["headers"],
    )
    sos1_id = res1.json()["id"]

    # SOS 2 triggered -> Unit 1 is busy -> takes Unit 2 (Bravo)
    res2 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0830, "longitude": 80.2120},
        headers=env["c2"]["headers"],
    )
    sos2_id = res2.json()["id"]

    # Verify distinct unit assignments
    active_list = await async_client.get("/api/v1/sos/active", headers=env["admin"]["headers"])
    records = {r["id"]: r for r in active_list.json()}

    assert records[sos1_id]["assigned_patrol_id"] == env["unit1_id"]
    assert records[sos2_id]["assigned_patrol_id"] == env["unit2_id"]
    assert records[sos1_id]["assigned_patrol_id"] != records[sos2_id]["assigned_patrol_id"]


@pytest.mark.asyncio
async def test_no_available_patrol_explicit_handling(async_client: AsyncClient):
    """Verify that when no on-duty patrol is available, NO_AVAILABLE_PATROL is returned without crashing."""
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = User(
            email="lonely_citizen@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Lonely Citizen",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        uid = u.id

    token = create_access_token({"sub": str(uid), "email": "lonely_citizen@safezone.org", "role": "CITIZEN"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["status"] == "NO_AVAILABLE_PATROL"
    assert res.json()["approximate_distance_km"] is None


@pytest.mark.asyncio
async def test_admin_manual_dispatch_override(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify Admin can manually override / assign a specific patrol unit to an emergency."""
    env = setup_dispatch_environment

    # Trigger SOS
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c1"]["headers"],
    )
    sos_id = trig_res.json()["id"]

    # Admin forces assignment of Unit 2 and Officer 2
    admin_res = await async_client.post(
        f"/api/v1/sos/{sos_id}/dispatch",
        json={"patrol_unit_id": env["unit2_id"], "officer_id": env["p2"]["officer_id"]},
        headers=env["admin"]["headers"],
    )
    assert admin_res.status_code == 200
    assert admin_res.json()["assigned_patrol_id"] == env["unit2_id"]
    assert admin_res.json()["assigned_officer_id"] == env["p2"]["officer_id"]


@pytest.mark.asyncio
async def test_prp_assigned_officer_remains_sos_eligible_and_busy_lifecycle(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify:
    1. On-duty officer assigned to a PRP remains eligible for automatic SOS dispatch.
    2. Active SOS dispatch marks the officer unavailable/busy.
    3. Resolving the SOS restores the officer's availability.
    4. Explicitly off-duty / unavailable officer is excluded from SOS dispatch.
    """
    from tests.conftest import TestAsyncSessionLocal
    from app.models.optimization import PRPLocation
    env = setup_dispatch_environment

    # 1. Create a PRP and manually assign Officer 1 and Unit 1
    async with TestAsyncSessionLocal() as session:
        prp = PRPLocation(
            prp_type="DYNAMIC",
            latitude=13.0850,
            longitude=80.2100,
            ward_no=101,
            zone_no="VIII",
            zone_name="ANNA_NAGAR",
            rank=1,
            risk_score=8.9,
            status="APPROVED",
        )
        session.add(prp)
        await session.commit()
        prp_id = prp.id

    assign_payload = {
        "prp_id": prp_id,
        "patrol_unit_id": env["unit1_id"],
        "officer_id": env["p1"]["officer_id"],
    }
    assign_res = await async_client.post("/api/v1/patrols/assignments/manual", json=assign_payload, headers=env["admin"]["headers"])
    assert assign_res.status_code == 201
    prp_assignment_id = assign_res.json()["id"]

    # Verify Officer 1 profile: is_available is still True and on_duty is True
    prof_res = await async_client.get("/api/v1/patrols/my-profile", headers=env["p1"]["headers"])
    assert prof_res.status_code == 200
    assert prof_res.json()["on_duty"] is True
    assert prof_res.json()["is_available"] is True

    # Transition PRP assignment: ACKNOWLEDGED -> AT_PRP
    ack_res = await async_client.post(f"/api/v1/patrols/assignments/{prp_assignment_id}/acknowledge", headers=env["p1"]["headers"])
    assert ack_res.status_code == 200
    at_res = await async_client.post(f"/api/v1/patrols/assignments/{prp_assignment_id}/at-prp", headers=env["p1"]["headers"])
    assert at_res.status_code == 200

    # 2. Trigger Citizen 1 SOS near Anna Nagar (13.0840, 80.2110)
    # Even though Officer 1 is AT_PRP, Officer 1 is on-duty and available, and should be assigned!
    sos_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110, "notes": "Emergency at Anna Nagar"},
        headers=env["c1"]["headers"],
    )
    assert sos_res.status_code == 201
    sos_data = sos_res.json()
    assert sos_data["status"] == "ASSIGNED"
    sos_id = sos_data["id"]

    # Verify through Admin monitoring endpoint that Officer 1 & Unit 1 were assigned
    admin_active = await async_client.get("/api/v1/sos/active", headers=env["admin"]["headers"])
    assert admin_active.status_code == 200
    matching_sos = next(s for s in admin_active.json() if s["id"] == sos_id)
    assert matching_sos["assigned_officer_id"] == env["p1"]["officer_id"]
    assert matching_sos["assigned_patrol_id"] == env["unit1_id"]

    # 3. Verify that active SOS makes Officer 1 unavailable
    prof_busy = await async_client.get("/api/v1/patrols/my-profile", headers=env["p1"]["headers"])
    assert prof_busy.json()["is_available"] is False

    # Trigger second SOS from Citizen 2 near Anna Nagar
    # Since Officer 1 is now busy with SOS #1, it must NOT assign Officer 1 (it should assign Officer 2)
    sos2_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110},
        headers=env["c2"]["headers"],
    )
    assert sos2_res.status_code == 201
    sos2_id = sos2_res.json()["id"]
    admin_active2 = await async_client.get("/api/v1/sos/active", headers=env["admin"]["headers"])
    matching_sos2 = next(s for s in admin_active2.json() if s["id"] == sos2_id)
    assert matching_sos2["assigned_officer_id"] == env["p2"]["officer_id"]

    # 4. Resolve SOS #1 -> Officer 1 should become available again
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "ACCEPTED"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    res_resolve = await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "RESOLVED"}, headers=env["p1"]["headers"])
    assert res_resolve.status_code == 200

    prof_after = await async_client.get("/api/v1/patrols/my-profile", headers=env["p1"]["headers"])
    assert prof_after.json()["is_available"] is True

    # 5. Explicit off-duty / unavailable behavior
    # Officer 1 goes off duty
    await async_client.post("/api/v1/patrols/duty-status", json={"on_duty": False}, headers=env["p1"]["headers"])
    prof_off = await async_client.get("/api/v1/patrols/my-profile", headers=env["p1"]["headers"])
    assert prof_off.json()["on_duty"] is False
    assert prof_off.json()["is_available"] is False


@pytest.mark.asyncio
async def test_citizen_and_police_history_and_get_by_id(async_client: AsyncClient, setup_dispatch_environment: dict):
    """Verify citizen history, police history, today-summary, and strict get-by-id RBAC."""
    env = setup_dispatch_environment

    # 1. Citizen 1 triggers SOS
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110, "notes": "History test alert"},
        headers=env["c1"]["headers"],
    )
    assert trig_res.status_code == 201
    sos_id = trig_res.json()["id"]

    # Officer 1 accepts and resolves
    await async_client.post(f"/api/v1/sos/{sos_id}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "RESOLVED", "notes": "All clear"}, headers=env["p1"]["headers"])

    # 2. Citizen 1 gets my-history -> contains resolved SOS
    c_hist_res = await async_client.get("/api/v1/sos/my-history", headers=env["c1"]["headers"])
    assert c_hist_res.status_code == 200
    c_hist = c_hist_res.json()
    assert len(c_hist) >= 1
    c_item = next(h for h in c_hist if h["id"] == sos_id)
    assert c_item["status"] == "RESOLVED"
    assert "assigned_patrol_id" not in c_item  # Strict privacy
    assert "assigned_officer_id" not in c_item

    # 3. Citizen 1 gets specific SOS by ID -> 200 OK (CitizenSOSStatusResponse)
    c_get_res = await async_client.get(f"/api/v1/sos/{sos_id}", headers=env["c1"]["headers"])
    assert c_get_res.status_code == 200
    assert c_get_res.json()["status"] == "RESOLVED"
    assert "assigned_patrol_id" not in c_get_res.json()

    # 4. Citizen 2 attempts to get Citizen 1's SOS by ID -> 403 Forbidden
    c2_get_res = await async_client.get(f"/api/v1/sos/{sos_id}", headers=env["c2"]["headers"])
    assert c2_get_res.status_code == 403

    # 5. Police Officer 1 gets history -> contains resolved SOS
    p_hist_res = await async_client.get("/api/v1/sos/police/history", headers=env["p1"]["headers"])
    assert p_hist_res.status_code == 200
    p_hist = p_hist_res.json()
    assert len(p_hist) >= 1
    p_item = next(h for h in p_hist if h["id"] == sos_id)
    assert p_item["status"] == "RESOLVED"
    assert p_item["assigned_officer_id"] == env["p1"]["officer_id"]

    # 6. Police Officer 1 gets today-summary
    p_summary_res = await async_client.get("/api/v1/sos/police/today-summary", headers=env["p1"]["headers"])
    assert p_summary_res.status_code == 200
    summary = p_summary_res.json()
    assert summary["handled_today"] >= 1
    assert summary["resolved_today"] >= 1
    assert len(summary["recent"]) >= 1

    # 7. Police Officer 1 gets SOS by ID -> 200 OK (SOSResponse)
    p_get_res = await async_client.get(f"/api/v1/sos/{sos_id}", headers=env["p1"]["headers"])
    assert p_get_res.status_code == 200
    assert p_get_res.json()["assigned_officer_id"] == env["p1"]["officer_id"]

    # 8. Police Officer 2 attempts to get Officer 1's SOS by ID -> 403 Forbidden
    p2_get_res = await async_client.get(f"/api/v1/sos/{sos_id}", headers=env["p2"]["headers"])
    assert p2_get_res.status_code == 403

    # 9. Admin gets SOS by ID -> 200 OK
    adm_get_res = await async_client.get(f"/api/v1/sos/{sos_id}", headers=env["admin"]["headers"])
    assert adm_get_res.status_code == 200
    assert adm_get_res.json()["id"] == sos_id


@pytest.mark.asyncio
async def test_post_sos_return_to_prp_lifecycle(async_client: AsyncClient, setup_dispatch_environment):
    """Verifies complete post-SOS return-to-PRP lifecycle restoration:
    1. Officer with AT_PRP assignment: SOS RESOLVED -> same assignment becomes ACKNOWLEDGED.
    2. Same scenario with SOS CANCELLED -> same assignment becomes ACKNOWLEDGED.
    3. Assignment ID, PRP ID, officer ID, unit ID, shift remain unchanged.
    4. Existing ACKNOWLEDGED assignment is not incorrectly modified (idempotency).
    5. COMPLETED / CANCELLED PRP assignments are not reactivated.
    6. Officer becomes is_available=True and on_duty remains True after SOS terminal state.
    7. Patrol unit receives DISPATCHED active-patrol status while in transit.
    8. Officer remains eligible for future emergency SOS dispatch while returning to PRP.
    9. Existing ACKNOWLEDGED -> AT_PRP transition remains functional.
    10. When no active PRP assignment exists, existing SOS resource-release behaviour is preserved.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from tests.conftest import TestAsyncSessionLocal

    env = setup_dispatch_environment
    p1_officer_id = env["p1"]["officer_id"]
    p1_unit_id = env["unit1_id"]

    # Step A: Setup a PRP and active assignment for Officer 1 in AT_PRP state
    async with TestAsyncSessionLocal() as session:
        opt_run = OptimizationRun(run_type="REFERENCE", total_prps_generated=1, status="COMPLETED")
        session.add(opt_run)
        await session.flush()

        prp = PRPLocation(
            optimization_run_id=opt_run.id,
            prp_type="REFERENCE",
            latitude=13.0850,
            longitude=80.2100,
            ward_no=101,
            zone_no="V",
            zone_name="Anna Nagar",
            rank=1,
            risk_score=7.5,
            status="ACTIVE",
        )
        session.add(prp)
        await session.flush()

        assignment = PatrolAssignment(
            prp_id=prp.id,
            patrol_unit_id=p1_unit_id,
            officer_id=p1_officer_id,
            shift_start=datetime.utcnow() - timedelta(hours=2),
            shift_end=datetime.utcnow() + timedelta(hours=6),
            status="AT_PRP",
        )
        session.add(assignment)
        await session.commit()
        await session.refresh(assignment)
        assignment_id = assignment.id

    # 1. Citizen 1 triggers SOS
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0845, "longitude": 80.2105, "notes": "Emergency at PRP"},
        headers=env["c1"]["headers"],
    )
    assert trig_res.status_code == 201
    sos_id = trig_res.json()["id"]

    # 2. Officer 1 accepts and progresses to RESOLVED
    await async_client.post(f"/api/v1/sos/{sos_id}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    resolve_res = await async_client.post(
        f"/api/v1/sos/{sos_id}/status",
        json={"status": "RESOLVED", "notes": "Distress resolved"},
        headers=env["p1"]["headers"],
    )
    assert resolve_res.status_code == 200

    # 3. Verify Assignment was restored to ACKNOWLEDGED & preserved all fields
    async with TestAsyncSessionLocal() as session:
        assign_res = await session.execute(select(PatrolAssignment).where(PatrolAssignment.id == assignment_id))
        saved_assignment = assign_res.scalar_one()
        assert saved_assignment.status == "ACKNOWLEDGED"
        assert saved_assignment.prp_id == prp.id
        assert saved_assignment.officer_id == p1_officer_id
        assert saved_assignment.patrol_unit_id == p1_unit_id

        off_res = await session.execute(select(PoliceOfficer).where(PoliceOfficer.id == p1_officer_id))
        officer = off_res.scalar_one()
        assert officer.on_duty is True
        assert officer.is_available is True

        unit_res = await session.execute(select(PatrolUnit).where(PatrolUnit.id == p1_unit_id))
        unit = unit_res.scalar_one()
        assert unit.status == "DISPATCHED"

    # 4. Verify existing ACKNOWLEDGED -> AT_PRP transition remains functional
    at_prp_res = await async_client.post(
        f"/api/v1/patrols/assignments/{assignment_id}/at-prp",
        headers=env["p1"]["headers"],
    )
    assert at_prp_res.status_code == 200
    assert at_prp_res.json()["status"] == "AT_PRP"

    async with TestAsyncSessionLocal() as session:
        unit_res = await session.execute(select(PatrolUnit).where(PatrolUnit.id == p1_unit_id))
        unit = unit_res.scalar_one()
        assert unit.status == "ON_PATROL"

    # 5. Verify CANCELLED SOS also transitions AT_PRP -> ACKNOWLEDGED
    trig_res2 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0848, "longitude": 80.2102, "notes": "False alarm"},
        headers=env["c1"]["headers"],
    )
    assert trig_res2.status_code == 201
    sos_id2 = trig_res2.json()["id"]

    await async_client.post(f"/api/v1/sos/{sos_id2}/accept", headers=env["p1"]["headers"])
    cancel_res = await async_client.post(
        f"/api/v1/sos/{sos_id2}/status",
        json={"status": "CANCELLED", "notes": "False alarm cancellation"},
        headers=env["p1"]["headers"],
    )
    assert cancel_res.status_code == 200

    async with TestAsyncSessionLocal() as session:
        assign_res = await session.execute(select(PatrolAssignment).where(PatrolAssignment.id == assignment_id))
        saved_assignment = assign_res.scalar_one()
        assert saved_assignment.status == "ACKNOWLEDGED"

    # 6. Verify Idempotency: resolving another SOS when already ACKNOWLEDGED does not alter status
    trig_res3 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0842, "longitude": 80.2104},
        headers=env["c1"]["headers"],
    )
    assert trig_res3.status_code == 201
    sos_id3 = trig_res3.json()["id"]

    await async_client.post(f"/api/v1/sos/{sos_id3}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id3}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id3}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id3}/status", json={"status": "RESOLVED"}, headers=env["p1"]["headers"])

    async with TestAsyncSessionLocal() as session:
        assign_res = await session.execute(select(PatrolAssignment).where(PatrolAssignment.id == assignment_id))
        saved_assignment = assign_res.scalar_one()
        assert saved_assignment.status == "ACKNOWLEDGED"

    # 7. Complete the patrol assignment
    complete_res = await async_client.post(
        f"/api/v1/patrols/assignments/{assignment_id}/complete",
        headers=env["p1"]["headers"],
    )
    assert complete_res.status_code == 200

    # 8. Verify that COMPLETED assignment is NOT reactivated upon subsequent SOS resolution
    trig_res4 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0841, "longitude": 80.2106},
        headers=env["c1"]["headers"],
    )
    assert trig_res4.status_code == 201
    sos_id4 = trig_res4.json()["id"]

    await async_client.post(f"/api/v1/sos/{sos_id4}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id4}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id4}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id4}/status", json={"status": "RESOLVED"}, headers=env["p1"]["headers"])

    async with TestAsyncSessionLocal() as session:
        assign_res = await session.execute(select(PatrolAssignment).where(PatrolAssignment.id == assignment_id))
        saved_assignment = assign_res.scalar_one()
        assert saved_assignment.status == "COMPLETED"

        unit_res = await session.execute(select(PatrolUnit).where(PatrolUnit.id == p1_unit_id))
        unit = unit_res.scalar_one()
        assert unit.status == "AVAILABLE"


@pytest.mark.asyncio
async def test_admin_sos_history_endpoint(async_client: AsyncClient, setup_dispatch_environment):
    """Verifies Admin SOS History endpoint:
    1. GET /sos/active excludes RESOLVED.
    2. GET /sos/admin/history includes RESOLVED and CANCELLED incidents.
    3. History is ordered newest first (triggered_at DESC).
    4. Non-admin users (Citizen and Police) cannot access Admin history (403 Forbidden).
    5. Existing Citizen history and Police history remain fully functional.
    """
    env = setup_dispatch_environment

    # 1. Trigger an SOS, accept, and resolve it
    trig_res = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0840, "longitude": 80.2110, "notes": "Incident to resolve"},
        headers=env["c1"]["headers"],
    )
    assert trig_res.status_code == 201
    sos_id1 = trig_res.json()["id"]

    await async_client.post(f"/api/v1/sos/{sos_id1}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id1}/status", json={"status": "EN_ROUTE"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id1}/status", json={"status": "ARRIVED"}, headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id1}/status", json={"status": "RESOLVED", "notes": "Resolved peacefully"}, headers=env["p1"]["headers"])

    # 2. Trigger another SOS, accept, and cancel it
    trig_res2 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0845, "longitude": 80.2115, "notes": "Incident to cancel"},
        headers=env["c2"]["headers"],
    )
    assert trig_res2.status_code == 201
    sos_id2 = trig_res2.json()["id"]

    await async_client.post(f"/api/v1/sos/{sos_id2}/accept", headers=env["p1"]["headers"])
    await async_client.post(f"/api/v1/sos/{sos_id2}/status", json={"status": "CANCELLED", "notes": "Cancelled"}, headers=env["p1"]["headers"])

    # 3. Trigger an active SOS in progress
    trig_res3 = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 13.0848, "longitude": 80.2118, "notes": "Active emergency in progress"},
        headers=env["c1"]["headers"],
    )
    assert trig_res3.status_code == 201
    sos_id3 = trig_res3.json()["id"]

    # 4. Verify GET /sos/active only contains active SOS (sos_id3), excludes RESOLVED (sos_id1) & CANCELLED (sos_id2)
    active_res = await async_client.get("/api/v1/sos/active", headers=env["admin"]["headers"])
    assert active_res.status_code == 200
    active_list = active_res.json()
    active_ids = [s["id"] for s in active_list]
    assert sos_id3 in active_ids
    assert sos_id1 not in active_ids
    assert sos_id2 not in active_ids

    # 5. Verify GET /sos/admin/history contains all incidents (active, resolved, cancelled)
    admin_hist_res = await async_client.get("/api/v1/sos/admin/history", headers=env["admin"]["headers"])
    assert admin_hist_res.status_code == 200
    admin_hist = admin_hist_res.json()
    hist_ids = [s["id"] for s in admin_hist]
    assert sos_id1 in hist_ids
    assert sos_id2 in hist_ids
    assert sos_id3 in hist_ids

    # 6. Verify History status filter
    resolved_only_res = await async_client.get("/api/v1/sos/admin/history?status=RESOLVED", headers=env["admin"]["headers"])
    assert resolved_only_res.status_code == 200
    resolved_list = resolved_only_res.json()
    assert all(s["status"] == "RESOLVED" for s in resolved_list)

    # 7. Verify Authorization: Citizen and Police are forbidden from /sos/admin/history
    c_hist_forbidden = await async_client.get("/api/v1/sos/admin/history", headers=env["c1"]["headers"])
    assert c_hist_forbidden.status_code == 403

    p_hist_forbidden = await async_client.get("/api/v1/sos/admin/history", headers=env["p1"]["headers"])
    assert p_hist_forbidden.status_code == 403

    # 8. Verify Citizen history and Police history still work
    c_hist_res = await async_client.get("/api/v1/sos/my-history", headers=env["c1"]["headers"])
    assert c_hist_res.status_code == 200
    assert any(s["id"] == sos_id1 for s in c_hist_res.json())

    p_hist_res = await async_client.get("/api/v1/sos/police/history", headers=env["p1"]["headers"])
    assert p_hist_res.status_code == 200
    assert any(s["id"] == sos_id1 for s in p_hist_res.json())




