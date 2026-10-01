import pytest
import pytest_asyncio
from httpx import AsyncClient
from datetime import date, time
from app.models.user import User, UserRole
from app.models.crime import CrimeIncident
from app.core.security import get_password_hash, create_access_token


@pytest_asyncio.fixture
async def admin_auth_header(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as session:
        admin = User(
            email="admin_crime@safezone.org",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Admin Crime Officer",
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
            email="citizen_crime@safezone.org",
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


@pytest.mark.asyncio
async def test_admin_create_crime_with_auto_classification(async_client: AsyncClient, admin_auth_header: dict):
    payload = {
        "description": "Complainant reported smart mobile phone and wallet taken from pocket in crowded commuter bus.",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "ward_no": 119,
        "zone_no": "IX",
        "zone_name": "TEYNAMPET",
        "occurred_date": "2026-09-15",
        "occurred_time": "14:30:00",
        "location_type": "BUS_STOP",
    }
    response = await async_client.post("/api/v1/crimes/", json=payload, headers=admin_auth_header)
    assert response.status_code == 201
    data = response.json()
    assert data["crime_category"] == "THEFT"
    assert data["severity"] == "MEDIUM"
    assert data["time_period"] == "AFTERNOON"
    assert data["predicted_category"] == "THEFT"
    assert data["confidence"] is not None
    assert data["classification_status"] in ["AUTO_CLASSIFIED", "REVIEW_REQUIRED"]
    assert "crime_id" in data


@pytest.mark.asyncio
async def test_citizen_cannot_create_crime(async_client: AsyncClient, citizen_auth_header: dict):
    payload = {
        "description": "Unauthorized attempt to create crime record.",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "ward_no": 119,
        "zone_no": "IX",
        "zone_name": "TEYNAMPET",
        "occurred_date": "2026-09-15",
        "occurred_time": "14:30:00",
    }
    response = await async_client.post("/api/v1/crimes/", json=payload, headers=citizen_auth_header)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_crime_incident_by_id(async_client: AsyncClient, admin_auth_header: dict):
    # Create incident
    payload = {
        "description": "Commercial warehouse broken into through back door overnight.",
        "crime_category": "BURGLARY",
        "severity": "HIGH",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "ward_no": 119,
        "zone_no": "IX",
        "zone_name": "TEYNAMPET",
        "occurred_date": "2026-09-10",
        "occurred_time": "03:15:00",
        "location_type": "COMMERCIAL_AREA",
    }
    create_res = await async_client.post("/api/v1/crimes/", json=payload, headers=admin_auth_header)
    created_id = create_res.json()["id"]
    crime_code = create_res.json()["crime_id"]

    # Fetch by integer PK
    get_res = await async_client.get(f"/api/v1/crimes/{created_id}", headers=admin_auth_header)
    assert get_res.status_code == 200
    assert get_res.json()["crime_category"] == "BURGLARY"

    # Fetch by string crime_id
    get_code_res = await async_client.get(f"/api/v1/crimes/{crime_code}", headers=admin_auth_header)
    assert get_code_res.status_code == 200
    assert get_code_res.json()["id"] == created_id


@pytest.mark.asyncio
async def test_list_crimes_with_filters_and_pagination(async_client: AsyncClient, admin_auth_header: dict):
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as session:
        c1 = CrimeIncident(
            crime_id="CR-FILTER-001",
            description="Robbery incident on dark road.",
            crime_category="ROBBERY",
            severity="HIGH",
            latitude=13.08,
            longitude=80.27,
            ward_no=50,
            zone_no="V",
            zone_name="ROYAPURAM",
            occurred_date=date(2026, 9, 1),
            occurred_time=time(22, 0),
            time_period="NIGHT",
            location_type="ROAD",
            reported_date=date(2026, 9, 1),
            status="REPORTED",
            classification_status="AUTO_CLASSIFIED",
        )
        c2 = CrimeIncident(
            crime_id="CR-FILTER-002",
            description="Cyber phishing incident.",
            crime_category="CYBERCRIME",
            severity="MEDIUM",
            latitude=13.09,
            longitude=80.28,
            ward_no=60,
            zone_no="V",
            zone_name="ROYAPURAM",
            occurred_date=date(2026, 9, 5),
            occurred_time=time(11, 0),
            time_period="MORNING",
            location_type="ONLINE",
            reported_date=date(2026, 9, 5),
            status="RESOLVED",
            classification_status="ADMIN_VERIFIED",
        )
        session.add_all([c1, c2])
        await session.commit()

    # Filter by category = ROBBERY
    res_cat = await async_client.get("/api/v1/crimes/?crime_category=ROBBERY", headers=admin_auth_header)
    assert res_cat.status_code == 200
    assert res_cat.json()["total"] == 1
    assert res_cat.json()["items"][0]["crime_id"] == "CR-FILTER-001"

    # Filter by severity = MEDIUM
    res_sev = await async_client.get("/api/v1/crimes/?severity=MEDIUM", headers=admin_auth_header)
    assert res_sev.status_code == 200
    assert res_sev.json()["total"] == 1
    assert res_sev.json()["items"][0]["crime_id"] == "CR-FILTER-002"

    # Filter by ward_no = 60
    res_ward = await async_client.get("/api/v1/crimes/?ward_no=60", headers=admin_auth_header)
    assert res_ward.status_code == 200
    assert res_ward.json()["total"] == 1


@pytest.mark.asyncio
async def test_admin_verify_classification_workflow(async_client: AsyncClient, admin_auth_header: dict):
    # Create incident with AUTO_CLASSIFIED / REVIEW_REQUIRED
    create_payload = {
        "description": "Suspicious person loitering and tailing individual.",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "ward_no": 119,
        "zone_no": "IX",
        "zone_name": "TEYNAMPET",
        "occurred_date": "2026-09-12",
        "occurred_time": "18:00:00",
    }
    create_res = await async_client.post("/api/v1/crimes/", json=create_payload, headers=admin_auth_header)
    incident_id = create_res.json()["id"]

    # Admin verifies and explicitly sets category to STALKING
    verify_payload = {
        "crime_category": "STALKING",
        "severity": "MEDIUM"
    }
    verify_res = await async_client.post(f"/api/v1/crimes/{incident_id}/verify", json=verify_payload, headers=admin_auth_header)
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["crime_category"] == "STALKING"
    assert data["classification_status"] == "ADMIN_VERIFIED"
    assert data["severity"] == "MEDIUM"


@pytest.mark.asyncio
async def test_delete_crime_incident(async_client: AsyncClient, admin_auth_header: dict):
    create_payload = {
        "description": "Public park bench vandalism.",
        "crime_category": "VANDALISM",
        "severity": "LOW",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "ward_no": 119,
        "zone_no": "IX",
        "zone_name": "TEYNAMPET",
        "occurred_date": "2026-09-12",
        "occurred_time": "19:00:00",
    }
    create_res = await async_client.post("/api/v1/crimes/", json=create_payload, headers=admin_auth_header)
    incident_id = create_res.json()["id"]

    # Delete
    del_res = await async_client.delete(f"/api/v1/crimes/{incident_id}", headers=admin_auth_header)
    assert del_res.status_code == 200

    # Confirm 404
    get_res = await async_client.get(f"/api/v1/crimes/{incident_id}", headers=admin_auth_header)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_classify_preview_endpoint(async_client: AsyncClient, admin_auth_header: dict):
    payload = {"description": "Pickpocket stole mobile phone and leather wallet from handbag on crowded bus."}
    response = await async_client.post("/api/v1/crimes/classify-preview", json=payload, headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_category"] == "THEFT"
    assert data["confidence"] > 0.75
    assert data["classification_status"] == "AUTO_CLASSIFIED"


@pytest.mark.asyncio
async def test_import_csv_and_duplicate_prevention(async_client: AsyncClient, admin_auth_header: dict):
    csv_content = """crime_id,description,crime_category,severity,latitude,longitude,ward_no,zone_no,zone_name,occurred_date,occurred_time,time_period,location_type,reported_date,status
CR-TEST-001,Unattended bag stolen from bench.,THEFT,MEDIUM,13.0827,80.2707,119,IX,TEYNAMPET,2026-09-01,10:00:00,MORNING,PARK,2026-09-01,REPORTED
CR-TEST-002,House break-in through terrace.,BURGLARY,HIGH,13.0850,80.2720,119,IX,TEYNAMPET,2026-09-02,02:00:00,NIGHT,RESIDENTIAL_AREA,2026-09-02,UNDER_INVESTIGATION
"""
    files = {"file": ("test_crimes.csv", csv_content.encode("utf-8"), "text/csv")}
    
    # 1. First import: 2 records imported
    res1 = await async_client.post("/api/v1/crimes/import-csv", files=files, headers=admin_auth_header)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["imported"] == 2
    assert data1["skipped_duplicates"] == 0

    # 2. Second import of same CSV: 2 duplicates skipped, 0 new imports
    files2 = {"file": ("test_crimes.csv", csv_content.encode("utf-8"), "text/csv")}
    res2 = await async_client.post("/api/v1/crimes/import-csv", files=files2, headers=admin_auth_header)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["imported"] == 0
    assert data2["skipped_duplicates"] == 2
