"""SafeZone Police, Patrol Resource and PRP Assignment Test Suite.

Verifies:
- Admin police account onboarding and badge uniqueness
- Citizen prevention from onboarding police or assigning patrols (403)
- Patrol unit resource registration and status management
- Manual PRP assignment and incompatible duplicate assignment prevention
- Automated OR-Tools assignment matching available resources to unassigned PRPs
- Complete assignment lifecycle transitions:
    ASSIGNED -> ACKNOWLEDGED -> AT_PRP -> COMPLETED
- Officer viewing their active assignment (/my-assignment)
- Cross-officer authorization boundaries.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.optimization import PRPLocation, PatrolAssignment
from app.core.security import get_password_hash, create_access_token


@pytest_asyncio.fixture
async def admin_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        admin = User(
            email="admin_patrols@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Admin Patrol Manager",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def citizen_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        citizen = User(
            email="citizen_patrols@safezone.org",
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
# 1. POLICE OFFICER ONBOARDING TESTS
# ==========================================

@pytest.mark.asyncio
async def test_admin_create_police_officer_success(async_client: AsyncClient, admin_auth_header: dict):
    """Verify admin can onboard a verified police officer."""
    payload = {
        "email": "officer.chennai1@safezone.org",
        "password": "OfficerPassword123!",
        "full_name": "Inspector R. Kumar",
        "phone_number": "9840112233",
        "badge_number": "TN-POL-1001",
        "rank": "Inspector",
        "station_name": "T. Nagar Police Station",
        "on_duty": True,
    }
    response = await async_client.post("/api/v1/admin/police", json=payload, headers=admin_auth_header)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "officer.chennai1@safezone.org"
    assert data["badge_number"] == "TN-POL-1001"
    assert data["rank"] == "Inspector"
    assert data["on_duty"] is True
    assert data["is_available"] is True


@pytest.mark.asyncio
async def test_duplicate_badge_or_email_rejected(async_client: AsyncClient, admin_auth_header: dict):
    """Verify system rejects duplicate officer badge or email."""
    payload = {
        "email": "officer.dup@safezone.org",
        "password": "OfficerPassword123!",
        "full_name": "Sub Inspector Anitha",
        "badge_number": "TN-POL-DUP",
        "rank": "Sub-Inspector",
        "station_name": "Adyar Police Station",
    }
    # First creation
    res1 = await async_client.post("/api/v1/admin/police", json=payload, headers=admin_auth_header)
    assert res1.status_code == 201

    # Duplicate email
    payload_dup_email = payload.copy()
    payload_dup_email["badge_number"] = "TN-POL-DIFF"
    res2 = await async_client.post("/api/v1/admin/police", json=payload_dup_email, headers=admin_auth_header)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()

    # Duplicate badge
    payload_dup_badge = payload.copy()
    payload_dup_badge["email"] = "officer.diff@safezone.org"
    res3 = await async_client.post("/api/v1/admin/police", json=payload_dup_badge, headers=admin_auth_header)
    assert res3.status_code == 400
    assert "already exists" in res3.json()["detail"].lower()


@pytest.mark.asyncio
async def test_citizen_cannot_manage_police_or_patrols(async_client: AsyncClient, citizen_auth_header: dict):
    """Verify citizen is blocked from administrative police/patrol management."""
    # Cannot create officer
    res1 = await async_client.post(
        "/api/v1/admin/police",
        json={"email": "c@safezone.org", "password": "Pass", "full_name": "X", "badge_number": "B1"},
        headers=citizen_auth_header,
    )
    assert res1.status_code == 403

    # Cannot assign patrol
    res2 = await async_client.post(
        "/api/v1/patrols/assignments/manual",
        json={"prp_id": 1, "patrol_unit_id": 1, "officer_id": 1},
        headers=citizen_auth_header,
    )
    assert res2.status_code == 403


# ==========================================
# 2. PATROL UNIT RESOURCE MANAGEMENT TESTS
# ==========================================

@pytest.mark.asyncio
async def test_admin_patrol_unit_crud(async_client: AsyncClient, admin_auth_header: dict):
    """Verify registration and status updates for patrol vehicle units."""
    create_payload = {
        "unit_code": "PATROL-CAR-01",
        "unit_type": "VEHICLE",
        "status": "AVAILABLE",
        "current_latitude": 13.0827,
        "current_longitude": 80.2707,
    }
    res = await async_client.post("/api/v1/admin/patrol-units", json=create_payload, headers=admin_auth_header)
    assert res.status_code == 201
    unit_id = res.json()["id"]

    # List units
    list_res = await async_client.get("/api/v1/admin/patrol-units?status=AVAILABLE", headers=admin_auth_header)
    assert list_res.status_code == 200
    assert any(u["unit_code"] == "PATROL-CAR-01" for u in list_res.json())

    # Update status
    update_res = await async_client.put(
        f"/api/v1/admin/patrol-units/{unit_id}",
        json={"status": "ON_PATROL"},
        headers=admin_auth_header,
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "ON_PATROL"


# ==========================================
# 3. MANUAL ASSIGNMENT & DUPLICATE PREVENTION
# ==========================================

@pytest.mark.asyncio
async def test_manual_assignment_and_duplicate_prevention(async_client: AsyncClient, admin_auth_header: dict):
    """Verify manual assignment to PRP and rejection of duplicate active assignments."""
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as session:
        # 1. Create PRP
        prp = PRPLocation(
            prp_type="DYNAMIC",
            latitude=13.0450,
            longitude=80.2650,
            ward_no=119,
            zone_no="IX",
            zone_name="TEYNAMPET",
            rank=1,
            risk_score=8.5,
            coverage_radius_km=3.0,
            status="APPROVED",
        )
        # 2. Create Unit
        unit = PatrolUnit(unit_code="PATROL-ALPHA-01", unit_type="VEHICLE", status="AVAILABLE")
        # 3. Create Officer
        u = User(email="officer.alpha@safezone.org", hashed_password="pwd", full_name="Officer Alpha", role=UserRole.POLICE, is_active=True)
        session.add_all([prp, unit, u])
        await session.commit()
        await session.refresh(u)

        officer = PoliceOfficer(user_id=u.id, badge_number="TN-POL-ALPHA", rank="SI", station_name="Teynampet", on_duty=True, is_available=True)
        session.add(officer)
        await session.commit()
        await session.refresh(prp)
        await session.refresh(unit)
        await session.refresh(officer)

        prp_id = prp.id
        unit_id = unit.id
        officer_id = officer.id

    # 1. Successful manual assignment
    payload = {
        "prp_id": prp_id,
        "patrol_unit_id": unit_id,
        "officer_id": officer_id,
        "shift_start": datetime.utcnow().isoformat(),
        "shift_end": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
    }
    assign_res = await async_client.post("/api/v1/patrols/assignments/manual", json=payload, headers=admin_auth_header)
    assert assign_res.status_code == 201
    data = assign_res.json()
    assert data["status"] == "ASSIGNED"
    assert data["prp_id"] == prp_id
    assert data["patrol_unit_id"] == unit_id
    assert data["officer_id"] == officer_id

    # 2. Duplicate assignment attempt with same unit -> Must fail 400
    dup_unit_res = await async_client.post("/api/v1/patrols/assignments/manual", json=payload, headers=admin_auth_header)
    assert dup_unit_res.status_code == 400
    assert "duplicate assignment" in dup_unit_res.json()["detail"].lower()


# ==========================================
# 4. AUTO-ASSIGNMENT OPTIMIZATION TESTS
# ==========================================

@pytest.mark.asyncio
async def test_auto_assignment_optimization(async_client: AsyncClient, admin_auth_header: dict):
    """Verify automated OR-Tools assignment solver pairs available units and officers to PRPs."""
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as session:
        # Create 2 unassigned PRPs
        p1 = PRPLocation(prp_type="DYNAMIC", latitude=13.080, longitude=80.270, ward_no=50, zone_no="V", zone_name="ROYAPURAM", rank=1, risk_score=9.0, status="APPROVED")
        p2 = PRPLocation(prp_type="DYNAMIC", latitude=13.040, longitude=80.250, ward_no=119, zone_no="IX", zone_name="TEYNAMPET", rank=2, risk_score=7.0, status="APPROVED")

        # Create 2 available units at distinct coordinates
        u1 = PatrolUnit(unit_code="AUTO-UNIT-1", unit_type="VEHICLE", status="AVAILABLE", current_latitude=13.081, current_longitude=80.271)
        u2 = PatrolUnit(unit_code="AUTO-UNIT-2", unit_type="VEHICLE", status="AVAILABLE", current_latitude=13.041, current_longitude=80.251)

        # Create 2 available on-duty officers
        user1 = User(email="officer.auto1@safezone.org", hashed_password="pwd", full_name="Officer Auto 1", role=UserRole.POLICE, is_active=True)
        user2 = User(email="officer.auto2@safezone.org", hashed_password="pwd", full_name="Officer Auto 2", role=UserRole.POLICE, is_active=True)
        session.add_all([p1, p2, u1, u2, user1, user2])
        await session.commit()
        await session.refresh(user1)
        await session.refresh(user2)

        off1 = PoliceOfficer(user_id=user1.id, badge_number="TN-AUTO-01", rank="HC", station_name="North", on_duty=True, is_available=True)
        off2 = PoliceOfficer(user_id=user2.id, badge_number="TN-AUTO-02", rank="HC", station_name="South", on_duty=True, is_available=True)
        session.add_all([off1, off2])
        await session.commit()

    # Trigger Auto-Assignment (POST /api/v1/patrols/assignments/auto)
    auto_res = await async_client.post(
        "/api/v1/patrols/assignments/auto",
        json={"shift_start": datetime.utcnow().isoformat()},
        headers=admin_auth_header,
    )
    assert auto_res.status_code == 201
    auto_data = auto_res.json()
    assert auto_data["assigned_count"] >= 2
    assert len(auto_data["assignments"]) >= 2

    # Check distinct units and officers assigned (no duplicate reuse)
    assigned_units = [a["patrol_unit_id"] for a in auto_data["assignments"]]
    assigned_officers = [a["officer_id"] for a in auto_data["assignments"]]
    assert len(assigned_units) == len(set(assigned_units))
    assert len(assigned_officers) == len(set(assigned_officers))


# ==========================================
# 5. ASSIGNMENT LIFECYCLE & POLICE WORKFLOW
# ==========================================

@pytest.mark.asyncio
async def test_officer_assignment_lifecycle_flow(async_client: AsyncClient, admin_auth_header: dict):
    """Verify full lifecycle: ASSIGNED -> ACKNOWLEDGED -> AT_PRP -> COMPLETED."""
    from tests.conftest import TestAsyncSessionLocal

    # 1. Setup Officer & Unit & PRP
    async with TestAsyncSessionLocal() as session:
        prp = PRPLocation(prp_type="DYNAMIC", latitude=13.05, longitude=80.25, ward_no=110, zone_no="IX", zone_name="TEYNAMPET", rank=1, risk_score=8.0, status="ACTIVE")
        unit = PatrolUnit(unit_code="UNIT-LIFE-01", unit_type="VEHICLE", status="AVAILABLE")
        u = User(email="officer.life@safezone.org", hashed_password=get_password_hash("LifePass123!"), full_name="Officer Lifecycle", role=UserRole.POLICE, is_active=True)
        session.add_all([prp, unit, u])
        await session.commit()
        await session.refresh(u)

        officer = PoliceOfficer(user_id=u.id, badge_number="TN-POL-LIFE", rank="SI", station_name="Central", on_duty=True, is_available=True)
        session.add(officer)
        await session.commit()
        await session.refresh(prp)
        await session.refresh(unit)
        await session.refresh(officer)

        prp_id = prp.id
        unit_id = unit.id
        officer_id = officer.id
        user_id = u.id

    # Officer JWT Token
    officer_token = create_access_token({"sub": str(user_id), "email": "officer.life@safezone.org", "role": "POLICE"})
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # 2. Admin creates assignment
    assign_payload = {"prp_id": prp_id, "patrol_unit_id": unit_id, "officer_id": officer_id}
    res_assign = await async_client.post("/api/v1/patrols/assignments/manual", json=assign_payload, headers=admin_auth_header)
    assert res_assign.status_code == 201
    assignment_id = res_assign.json()["id"]

    # 3. Officer views active deployment (GET /api/v1/patrols/my-assignment)
    my_res = await async_client.get("/api/v1/patrols/my-assignment", headers=officer_headers)
    assert my_res.status_code == 200
    assert my_res.json()["id"] == assignment_id
    assert my_res.json()["status"] == "ASSIGNED"

    # 4. Officer acknowledges (POST /api/v1/patrols/assignments/{id}/acknowledge)
    ack_res = await async_client.post(f"/api/v1/patrols/assignments/{assignment_id}/acknowledge", headers=officer_headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 5. Officer arrives at PRP (POST /api/v1/patrols/assignments/{id}/at-prp)
    at_res = await async_client.post(f"/api/v1/patrols/assignments/{assignment_id}/at-prp", headers=officer_headers)
    assert at_res.status_code == 200
    assert at_res.json()["status"] == "AT_PRP"

    # 6. Officer completes assignment (POST /api/v1/patrols/assignments/{id}/complete)
    comp_res = await async_client.post(f"/api/v1/patrols/assignments/{assignment_id}/complete", headers=officer_headers)
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "COMPLETED"

    # 7. Unit is released and back to AVAILABLE
    unit_res = await async_client.get("/api/v1/admin/patrol-units?status=AVAILABLE", headers=admin_auth_header)
    assert unit_res.status_code == 200
    assert any(u["unit_code"] == "UNIT-LIFE-01" and u["status"] == "AVAILABLE" for u in unit_res.json())


@pytest.mark.asyncio
async def test_police_profile_duty_and_location_endpoints(async_client: AsyncClient, admin_auth_header: dict):
    """Verify police officer can fetch profile, toggle duty status, and send location updates."""
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = User(
            email="officer.mobile@safezone.org",
            hashed_password=get_password_hash("MobilePass123!"),
            full_name="Officer Mobile Test",
            role=UserRole.POLICE,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)

        officer = PoliceOfficer(
            user_id=u.id,
            badge_number="TN-POL-MOB",
            rank="Sub-Inspector",
            station_name="T. Nagar Mobile",
            on_duty=False,
            is_available=False,
        )
        session.add(officer)
        await session.commit()
        user_id = u.id

    token = create_access_token({"sub": str(user_id), "email": "officer.mobile@safezone.org", "role": "POLICE"})
    officer_headers = {"Authorization": f"Bearer {token}"}

    # 1. Get profile
    res_prof = await async_client.get("/api/v1/patrols/my-profile", headers=officer_headers)
    assert res_prof.status_code == 200
    assert res_prof.json()["badge_number"] == "TN-POL-MOB"
    assert res_prof.json()["on_duty"] is False

    # 2. Toggle duty status to ON_DUTY
    res_duty = await async_client.post("/api/v1/patrols/duty-status", json={"on_duty": True, "is_available": True}, headers=officer_headers)
    assert res_duty.status_code == 200
    assert res_duty.json()["on_duty"] is True
    assert res_duty.json()["is_available"] is True

    # 3. Send location update
    res_loc = await async_client.post("/api/v1/patrols/location", json={"latitude": 13.0827, "longitude": 80.2707}, headers=officer_headers)
    assert res_loc.status_code == 200
    assert res_loc.json()["status"] == "success"
    assert res_loc.json()["latitude"] == 13.0827


@pytest.mark.asyncio
async def test_police_sos_flow(async_client: AsyncClient):
    """Verify police officer can list active SOS, accept dispatch, progress lifecycle, and resolve."""
    from tests.conftest import TestAsyncSessionLocal
    from app.models.sos import SOSRequest
    async with TestAsyncSessionLocal() as session:
        citizen = User(
            email="citizen_sos@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Citizen in Distress",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        officer_user = User(
            email="officer_sos@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Responding Officer",
            role=UserRole.POLICE,
            is_active=True,
        )
        session.add_all([citizen, officer_user])
        await session.commit()
        await session.refresh(citizen)
        await session.refresh(officer_user)

        officer = PoliceOfficer(
            user_id=officer_user.id,
            badge_number="TN-POL-SOS",
            rank="Inspector",
            station_name="SOS Station",
            on_duty=True,
            is_available=True,
        )
        session.add(officer)

        sos = SOSRequest(
            citizen_id=citizen.id,
            latitude=13.0400,
            longitude=80.2500,
            status="ACTIVE",
            notes="Immediate assistance needed",
        )
        session.add(sos)
        await session.commit()
        await session.refresh(sos)
        sos_id = sos.id
        officer_user_id = officer_user.id

    token = create_access_token({"sub": str(officer_user_id), "email": "officer_sos@safezone.org", "role": "POLICE"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. List active SOS
    res_list = await async_client.get("/api/v1/sos/active", headers=headers)
    assert res_list.status_code == 200
    assert any(s["id"] == sos_id for s in res_list.json())

    # 2. Accept SOS
    res_accept = await async_client.post(f"/api/v1/sos/{sos_id}/accept", headers=headers)
    assert res_accept.status_code == 200
    assert res_accept.json()["status"] == "ACCEPTED"

    # 3. Mark En Route
    res_enroute = await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "EN_ROUTE"}, headers=headers)
    assert res_enroute.status_code == 200
    assert res_enroute.json()["status"] == "EN_ROUTE"

    # 4. Mark Arrived
    res_arrived = await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "ARRIVED"}, headers=headers)
    assert res_arrived.status_code == 200
    assert res_arrived.json()["status"] == "ARRIVED"

    # 5. Mark Resolved
    res_resolved = await async_client.post(f"/api/v1/sos/{sos_id}/status", json={"status": "RESOLVED", "notes": "Citizen safe"}, headers=headers)
    assert res_resolved.status_code == 200
    assert res_resolved.json()["status"] == "RESOLVED"

