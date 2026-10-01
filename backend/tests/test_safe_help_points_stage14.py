"""SafeZone Stage 14 — Safe Help Points Finalization Test Suite.

Verifies:
1. Admin CRUD: create, edit, verify toggle, deactivate toggle, delete, list.
2. Citizen Filtering: citizen endpoint returns ONLY verified AND active Safe Help Points.
3. Verification/Active Security: citizens cannot bypass verification or active filters via query parameters.
4. Role-based Access Control: non-admins cannot mutate or import Safe Help Points (403 Forbidden).
5. Zero PRP Leakage: help point payloads never expose PRP coordinates, risk scores, or tactical patrol data.
6. CSV Import Validation: schema checking, coordinate range validation, duplicate skipping, and invalid row reporting.
"""

import io
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.help_point import SafeHelpPoint
from app.core.security import create_access_token, get_password_hash
from tests.conftest import TestAsyncSessionLocal


@pytest_asyncio.fixture
async def setup_shp_users():

    """Setup Admin, Citizen, and Police users with JWT tokens."""
    async with TestAsyncSessionLocal() as db:
        admin = User(
            email="admin.shp@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Admin SHP Manager",
            role=UserRole.ADMIN,
            is_active=True,
        )
        citizen = User(
            email="citizen.shp@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="Citizen User",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        police = User(
            email="police.shp@safezone.org",
            hashed_password=get_password_hash("PolicePass123!"),
            full_name="Police User",
            role=UserRole.POLICE,
            is_active=True,
        )
        db.add_all([admin, citizen, police])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(citizen)
        await db.refresh(police)

        admin_token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": "admin"})
        citizen_token = create_access_token({"sub": str(citizen.id), "email": citizen.email, "role": "citizen"})
        police_token = create_access_token({"sub": str(police.id), "email": police.email, "role": "police"})

        return {
            "admin": admin,
            "citizen": citizen,
            "police": police,
            "admin_token": admin_token,
            "citizen_token": citizen_token,
            "police_token": police_token,
        }


@pytest.mark.asyncio
async def test_admin_shp_crud_and_lifecycle(async_client: AsyncClient, setup_shp_users):
    """Test Admin create, update, verify toggle, deactivate toggle, and delete."""
    u = setup_shp_users
    admin_headers = {"Authorization": f"Bearer {u['admin_token']}"}

    # 1. Admin Create Safe Help Point
    create_payload = {
        "name": "Rajiv Gandhi Government General Hospital",
        "facility_type": "HOSPITAL",
        "latitude": 13.0805,
        "longitude": 80.2785,
        "address": "EVR Periyar Salai, Park Town, Chennai",
        "phone_number": "+91 44 2530 5000",
        "is_verified": True,
        "is_active": True,
    }
    create_res = await async_client.post("/api/v1/help-points/", headers=admin_headers, json=create_payload)
    assert create_res.status_code == 201
    shp = create_res.json()
    shp_id = shp["id"]
    assert shp["name"] == "Rajiv Gandhi Government General Hospital"
    assert shp["facility_type"] == "HOSPITAL"
    assert shp["is_verified"] is True
    assert shp["is_active"] is True
    assert "map_link" in shp

    # 2. Admin Update Safe Help Point
    update_res = await async_client.put(
        f"/api/v1/help-points/{shp_id}",
        headers=admin_headers,
        json={"phone_number": "+91 44 2530 5555", "address": "Park Town, Chennai 600003"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["phone_number"] == "+91 44 2530 5555"

    # 3. Admin Toggle Verification (True -> False)
    verify_res = await async_client.post(f"/api/v1/help-points/{shp_id}/verify", headers=admin_headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["is_verified"] is False

    # 4. Admin Toggle Deactivation (True -> False)
    deact_res = await async_client.post(f"/api/v1/help-points/{shp_id}/deactivate", headers=admin_headers)
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 5. Admin Reactivate and Verify
    await async_client.post(f"/api/v1/help-points/{shp_id}/verify", headers=admin_headers)
    await async_client.post(f"/api/v1/help-points/{shp_id}/deactivate", headers=admin_headers)

    # 6. Admin Delete Safe Help Point
    del_res = await async_client.delete(f"/api/v1/help-points/{shp_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]


@pytest.mark.asyncio
async def test_citizen_strict_verified_and_active_filtering(async_client: AsyncClient, setup_shp_users):
    """Verify that Citizens and unauthenticated callers receive ONLY verified and active facilities."""
    u = setup_shp_users
    admin_headers = {"Authorization": f"Bearer {u['admin_token']}"}
    citizen_headers = {"Authorization": f"Bearer {u['citizen_token']}"}

    # Setup 4 test facilities in DB:
    # 1. Verified & Active (Should be visible to citizen)
    # 2. Verified & Inactive (Should be hidden from citizen)
    # 3. Unverified & Active (Should be hidden from citizen)
    # 4. Unverified & Inactive (Should be hidden from citizen)
    async with TestAsyncSessionLocal() as db:
        f1 = SafeHelpPoint(name="Visible Center", facility_type="HOSPITAL", latitude=13.08, longitude=80.27, is_verified=True, is_active=True)
        f2 = SafeHelpPoint(name="Inactive Center", facility_type="POLICE_STATION", latitude=13.09, longitude=80.28, is_verified=True, is_active=False)
        f3 = SafeHelpPoint(name="Pending Center", facility_type="POLICE_BOOTH", latitude=13.10, longitude=80.29, is_verified=False, is_active=True)
        f4 = SafeHelpPoint(name="Disabled Pending Center", facility_type="EMERGENCY_FACILITY", latitude=13.11, longitude=80.30, is_verified=False, is_active=False)
        db.add_all([f1, f2, f3, f4])
        await db.commit()
        await db.refresh(f1)
        await db.refresh(f2)
        await db.refresh(f3)
        await db.refresh(f4)
        f1_id, f2_id, f3_id = f1.id, f2.id, f3.id

    # 1. Citizen queries all help points
    cit_res = await async_client.get("/api/v1/help-points/", headers=citizen_headers)
    assert cit_res.status_code == 200
    cit_points = cit_res.json()
    cit_names = [p["name"] for p in cit_points]
    assert "Visible Center" in cit_names
    assert "Inactive Center" not in cit_names
    assert "Pending Center" not in cit_names
    assert "Disabled Pending Center" not in cit_names

    # 2. Citizen attempts to bypass filters by passing query parameters
    bypass_res = await async_client.get("/api/v1/help-points/?is_verified=false&is_active=false", headers=citizen_headers)
    assert bypass_res.status_code == 200
    bypass_names = [p["name"] for p in bypass_res.json()]
    assert "Visible Center" in bypass_names
    assert "Inactive Center" not in bypass_names
    assert "Pending Center" not in bypass_names

    # 3. Single item retrieval by ID
    # Verified active point -> OK
    f1_res = await async_client.get(f"/api/v1/help-points/{f1_id}", headers=citizen_headers)
    assert f1_res.status_code == 200
    assert f1_res.json()["name"] == "Visible Center"

    # Inactive point -> 404 for citizen
    f2_res = await async_client.get(f"/api/v1/help-points/{f2_id}", headers=citizen_headers)
    assert f2_res.status_code == 404

    # Unverified point -> 404 for citizen
    f3_res = await async_client.get(f"/api/v1/help-points/{f3_id}", headers=citizen_headers)
    assert f3_res.status_code == 404

    # 4. Admin CAN view all 4 points with explicit filters
    admin_all_res = await async_client.get("/api/v1/help-points/?is_verified=false", headers=admin_headers)
    assert admin_all_res.status_code == 200
    admin_unverified_names = [p["name"] for p in admin_all_res.json()]
    assert "Pending Center" in admin_unverified_names


@pytest.mark.asyncio
async def test_non_admin_mutation_blocked(async_client: AsyncClient, setup_shp_users):
    """Verify that Citizen and Police roles are forbidden from mutating Safe Help Points."""
    u = setup_shp_users
    citizen_headers = {"Authorization": f"Bearer {u['citizen_token']}"}
    police_headers = {"Authorization": f"Bearer {u['police_token']}"}

    payload = {"name": "Unauthorized Facility", "facility_type": "HOSPITAL", "latitude": 13.08, "longitude": 80.27}

    # Citizen POST -> 403
    assert (await async_client.post("/api/v1/help-points/", headers=citizen_headers, json=payload)).status_code == 403
    # Police POST -> 403
    assert (await async_client.post("/api/v1/help-points/", headers=police_headers, json=payload)).status_code == 403
    # Citizen PUT -> 403
    assert (await async_client.put("/api/v1/help-points/1", headers=citizen_headers, json=payload)).status_code == 403
    # Citizen DELETE -> 403
    assert (await async_client.delete("/api/v1/help-points/1", headers=citizen_headers)).status_code == 403
    # Citizen Verify -> 403
    assert (await async_client.post("/api/v1/help-points/1/verify", headers=citizen_headers)).status_code == 403
    # Citizen Deactivate -> 403
    assert (await async_client.post("/api/v1/help-points/1/deactivate", headers=citizen_headers)).status_code == 403


@pytest.mark.asyncio
async def test_shp_csv_import_validation_and_reporting(async_client: AsyncClient, setup_shp_users):
    """Test CSV import schema validation, coordinate bounds checking, duplicate handling, and error reporting."""
    u = setup_shp_users
    admin_headers = {"Authorization": f"Bearer {u['admin_token']}"}

    csv_content = (
        "name,facility_type,latitude,longitude,address,phone_number,is_verified,is_active\n"
        "Stanley Medical College Hospital,HOSPITAL,13.1075,80.2872,Old Jail Rd Royapuram,+91 44 2528 1351,true,true\n"
        "Royapuram Police Station,POLICE_STATION,13.1090,80.2910,Royapuram Chennai,112,true,true\n"
        "Invalid Coord Hospital,HOSPITAL,999.00,80.28,Invalid Lat Address,,true,true\n"
        ",POLICE_BOOTH,13.10,80.29,Empty Name Address,,true,true\n"
        "Stanley Medical College Hospital,HOSPITAL,13.1075,80.2872,Duplicate Name,,true,true\n"
    )

    files = {"file": ("test_help_points.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    import_res = await async_client.post("/api/v1/help-points/import-csv", headers=admin_headers, files=files)
    assert import_res.status_code == 200
    summary = import_res.json()

    assert summary["total_rows"] == 5
    assert summary["imported"] == 2  # Stanley Medical College Hospital & Royapuram Police Station
    assert summary["skipped_duplicates"] == 1  # Second Stanley row
    assert len(summary["errors"]) == 2  # Invalid Coord (Row 3) and Empty Name (Row 4)
    assert any("out of range" in err for err in summary["errors"])
    assert any("Empty facility name" in err for err in summary["errors"])


@pytest.mark.asyncio
async def test_shp_never_leaks_prp_or_tactical_data(async_client: AsyncClient, setup_shp_users):
    """Strict test verifying Safe Help Point model and endpoints have zero leakage of PRP attributes."""
    u = setup_shp_users
    citizen_headers = {"Authorization": f"Bearer {u['citizen_token']}"}

    async with TestAsyncSessionLocal() as db:
        shp = SafeHelpPoint(
            name="Kilpauk Medical College Hospital",
            facility_type="HOSPITAL",
            latitude=13.0805,
            longitude=80.2435,
            address="Poonamallee High Rd, Kilpauk",
            phone_number="+91 44 2836 4951",
            is_verified=True,
            is_active=True,
        )
        db.add(shp)
        await db.commit()
        await db.refresh(shp)

    res = await async_client.get(f"/api/v1/help-points/{shp.id}", headers=citizen_headers)
    assert res.status_code == 200
    data = res.json()

    # Forbidden tactical PRP / police fields
    forbidden_keys = [
        "prp_id", "rank", "risk_score", "coverage_radius_km",
        "optimization_run_id", "assigned_patrol_id", "officer_id",
        "unit_code", "badge_number", "tactical_score"
    ]
    for key in forbidden_keys:
        assert key not in data, f"Strategic PRP leakage detected: key '{key}' found in Safe Help Point response!"
