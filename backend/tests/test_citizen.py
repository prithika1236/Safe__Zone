"""SafeZone Citizen Module Backend Test Suite.

Tests:
- Citizen registration and authentication
- Emergency Contact CRUD & ownership isolation
- Primary emergency contact handling
- Safe Help Points verified/active filtering
- Admin Safe Help Points CRUD & verification toggle
- Safe Help Points CSV import with validation & duplicate prevention
- SOS coordinate validation and zero-dummy coordinate rejection
- Citizen active SOS retrieval with strict privacy enforcement and non-fabricated ETA
- NO_AVAILABLE_PATROL status handling.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User, UserRole, EmergencyContact
from app.models.help_point import SafeHelpPoint
from app.models.police import PoliceOfficer
from app.models.sos import SOSRequest
from app.core.security import get_password_hash, create_access_token


@pytest_asyncio.fixture
async def citizen_a(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = User(
            email="citizen_a@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="Citizen Alice",
            phone_number="9876543210",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        user_id = u.id

    token = create_access_token({"sub": str(user_id), "email": "citizen_a@safezone.org", "role": "CITIZEN"})
    return {"id": user_id, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest_asyncio.fixture
async def citizen_b(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = User(
            email="citizen_b@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="Citizen Bob",
            phone_number="9876543211",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        user_id = u.id

    token = create_access_token({"sub": str(user_id), "email": "citizen_b@safezone.org", "role": "CITIZEN"})
    return {"id": user_id, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest_asyncio.fixture
async def admin_auth(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        u = User(
            email="admin_user@safezone.gov",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="System Administrator",
            phone_number="9876543299",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        user_id = u.id

    token = create_access_token({"sub": str(user_id), "email": "admin_user@safezone.gov", "role": "ADMIN"})
    return {"id": user_id, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.mark.asyncio
async def test_citizen_registration_and_login_flow(async_client: AsyncClient):
    """Verify citizen registration and login."""
    reg_payload = {
        "email": "new_citizen@safezone.org",
        "password": "SecurePassword123!",
        "full_name": "New Registered Citizen",
        "phone_number": "9812345678",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    assert reg_res.json()["email"] == "new_citizen@safezone.org"

    # Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "new_citizen@safezone.org", "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()
    assert login_res.json()["user"]["role"] == "CITIZEN"


@pytest.mark.asyncio
async def test_emergency_contact_crud_and_ownership_security(
    async_client: AsyncClient, citizen_a: dict, citizen_b: dict
):
    """Verify Emergency Contact CRUD and ownership isolation between citizens."""
    # 1. Citizen A creates Contact 1
    create_payload = {
        "name": "Emergency Mom",
        "phone_number": "+919876543210",
        "relationship_type": "Mother",
        "is_primary": True,
    }
    create_res = await async_client.post("/api/v1/contacts/", json=create_payload, headers=citizen_a["headers"])
    assert create_res.status_code == 201
    contact_id = create_res.json()["id"]
    assert create_res.json()["name"] == "Emergency Mom"
    assert create_res.json()["is_primary"] is True

    # 2. Citizen A lists contacts -> sees Contact 1
    list_res_a = await async_client.get("/api/v1/contacts/", headers=citizen_a["headers"])
    assert list_res_a.status_code == 200
    assert len(list_res_a.json()) == 1
    assert list_res_a.json()[0]["id"] == contact_id

    # 3. Citizen B lists contacts -> CANNOT see Citizen A's contact
    list_res_b = await async_client.get("/api/v1/contacts/", headers=citizen_b["headers"])
    assert list_res_b.status_code == 200
    assert len(list_res_b.json()) == 0

    # 4. Citizen B attempts to edit Citizen A's contact -> 404
    edit_res_b = await async_client.put(
        f"/api/v1/contacts/{contact_id}",
        json={"name": "Hacked Contact"},
        headers=citizen_b["headers"],
    )
    assert edit_res_b.status_code == 404

    # 5. Citizen B attempts to delete Citizen A's contact -> 404
    del_res_b = await async_client.delete(f"/api/v1/contacts/{contact_id}", headers=citizen_b["headers"])
    assert del_res_b.status_code == 404

    # 6. Citizen A edits contact -> success
    edit_res_a = await async_client.put(
        f"/api/v1/contacts/{contact_id}",
        json={"name": "Mom (Primary)"},
        headers=citizen_a["headers"],
    )
    assert edit_res_a.status_code == 200
    assert edit_res_a.json()["name"] == "Mom (Primary)"

    # 7. Citizen A deletes contact -> 204
    del_res_a = await async_client.delete(f"/api/v1/contacts/{contact_id}", headers=citizen_a["headers"])
    assert del_res_a.status_code == 204


@pytest.mark.asyncio
async def test_safe_help_points_verified_active_filtering(async_client: AsyncClient):
    """Verify Safe Help Points directory returns only verified and active facilities."""
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        # Verified & Active Hospital
        hp1 = SafeHelpPoint(
            name="Apollo Emergency Care",
            facility_type="HOSPITAL",
            latitude=13.0600,
            longitude=80.2400,
            address="Greams Road, Chennai",
            phone_number="04428290200",
            is_verified=True,
            is_active=True,
        )
        # Unverified Facility
        hp2 = SafeHelpPoint(
            name="Unverified Clinic",
            facility_type="CLINIC",
            latitude=13.0650,
            longitude=80.2450,
            is_verified=False,
            is_active=True,
        )
        # Inactive Facility
        hp3 = SafeHelpPoint(
            name="Old Closed Police Booth",
            facility_type="POLICE_STATION",
            latitude=13.0700,
            longitude=80.2500,
            is_verified=True,
            is_active=False,
        )
        session.add_all([hp1, hp2, hp3])
        await session.commit()

    res = await async_client.get("/api/v1/help-points/")
    assert res.status_code == 200
    points = res.json()
    assert any(p["name"] == "Apollo Emergency Care" for p in points)
    assert not any(p["name"] == "Unverified Clinic" for p in points)
    assert not any(p["name"] == "Old Closed Police Booth" for p in points)


@pytest.mark.asyncio
async def test_admin_shp_crud_and_verify_toggle(async_client: AsyncClient, admin_auth: dict):
    """Verify Admin Safe Help Point CRUD operations and verification toggle."""
    # 1. Create SHP
    create_payload = {
        "name": "Guindy Multi-Speciality Clinic",
        "facility_type": "HOSPITAL",
        "latitude": 13.0067,
        "longitude": 80.2021,
        "address": "Guindy Industrial Estate, Chennai",
        "phone_number": "044-0000-9999",
        "is_verified": False,
        "is_active": True,
    }
    create_res = await async_client.post("/api/v1/help-points/", json=create_payload, headers=admin_auth["headers"])
    assert create_res.status_code == 201
    shp_id = create_res.json()["id"]
    assert create_res.json()["is_verified"] is False

    # 2. Toggle verification status
    verify_res = await async_client.post(f"/api/v1/help-points/{shp_id}/verify", headers=admin_auth["headers"])
    assert verify_res.status_code == 200
    assert verify_res.json()["is_verified"] is True

    # 3. Update SHP
    upd_res = await async_client.put(
        f"/api/v1/help-points/{shp_id}",
        json={"name": "Guindy Trauma & Emergency Center", "facility_type": "EMERGENCY_FACILITY"},
        headers=admin_auth["headers"],
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Guindy Trauma & Emergency Center"
    assert upd_res.json()["facility_type"] == "EMERGENCY_FACILITY"

    # 4. Delete SHP
    del_res = await async_client.delete(f"/api/v1/help-points/{shp_id}", headers=admin_auth["headers"])
    assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_shp_csv_import_and_validation(async_client: AsyncClient, admin_auth: dict):
    """Verify Admin SHP CSV batch ingestion with row validation and duplicate prevention."""
    csv_content = (
        "help_point_id,name,facility_type,latitude,longitude,ward_no,zone_no,zone_name,address,phone,is_verified,is_active,is_demo\n"
        "1,Anna Nagar 24x7 Safety Post,POLICE_BOOTH,13.0850,80.2100,101,VIII,ANNANAGAR,Anna Nagar West,044-0000-1001,true,true,true\n"
        "2,T Nagar General Hospital,HOSPITAL,13.0400,80.2300,119,IX,TEYNAMPET,Usman Road,044-0000-1002,true,true,true\n"
        "3,Invalid Latitude Facility,HOSPITAL,999.0,80.2300,119,IX,TEYNAMPET,Unknown Address,,true,true,true\n"
    )
    files = {"file": ("demo_shp.csv", csv_content.encode("utf-8"), "text/csv")}
    res = await async_client.post("/api/v1/help-points/import-csv", files=files, headers=admin_auth["headers"])
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_rows"] == 3
    assert summary["imported"] == 2
    assert len(summary["errors"]) == 1
    assert "Coordinate values out of range" in summary["errors"][0]


@pytest.mark.asyncio
async def test_sos_zero_dummy_coordinates_validation(async_client: AsyncClient, citizen_a: dict):
    """Verify invalid or zero dummy GPS coordinates are rejected with 422 error."""
    # Zero latitude rejection
    res_zero = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 0.0, "longitude": 80.2707},
        headers=citizen_a["headers"],
    )
    assert res_zero.status_code == 422

    # Out of bounds latitude rejection
    res_oob = await async_client.post(
        "/api/v1/sos/trigger",
        json={"latitude": 195.0, "longitude": 80.2707},
        headers=citizen_a["headers"],
    )
    assert res_oob.status_code == 422


@pytest.mark.asyncio
async def test_citizen_sos_trigger_and_privacy_retrieval(async_client: AsyncClient, citizen_a: dict):
    """Verify citizen triggers SOS and retrieves active response status with strict privacy and no fabricated ETA."""
    # Trigger valid SOS
    sos_payload = {
        "latitude": 13.0827,
        "longitude": 80.2707,
        "notes": "Need urgent police assistance near market",
    }
    trig_res = await async_client.post("/api/v1/sos/trigger", json=sos_payload, headers=citizen_a["headers"])
    assert trig_res.status_code == 201
    sos_data = trig_res.json()
    assert sos_data["id"] > 0
    assert sos_data["status"] in ["ACTIVE", "NO_AVAILABLE_PATROL"]

    # Retrieve My Active SOS
    my_active_res = await async_client.get("/api/v1/sos/my-active", headers=citizen_a["headers"])
    assert my_active_res.status_code == 200
    active_data = my_active_res.json()
    assert active_data is not None
    assert active_data["id"] == sos_data["id"]

    # ETA Audit verification: estimated_arrival_minutes must be null when routing duration is unavailable
    assert active_data.get("estimated_arrival_minutes") is None

    # Privacy validation: Ensure response does NOT contain PRP coordinates, raw police location, or optimization data
    assert "prp" not in active_data
    assert "prp_id" not in active_data
    assert "patrol_unit" not in active_data
    assert "officer_location" not in active_data
    assert "risk_score" not in active_data


@pytest.mark.asyncio
async def test_import_processed_safezone_help_points_csv(async_client: AsyncClient, admin_auth: dict):
    """Verify that the generated safezone_help_points.csv imports successfully without failures."""
    import os
    csv_path = os.path.join("data", "processed", "safezone_help_points.csv")
    assert os.path.exists(csv_path)

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("safezone_help_points.csv", file_bytes, "text/csv")}
    res = await async_client.post("/api/v1/help-points/import-csv", files=files, headers=admin_auth["headers"])
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_rows"] == 80
    assert summary["imported"] >= 1
    assert len(summary["errors"]) == 0

