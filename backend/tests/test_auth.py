import pytest
from httpx import AsyncClient
from app.models.user import User, UserRole
from app.core.security import get_password_hash, create_access_token


@pytest.mark.asyncio
async def test_citizen_registration_success(async_client: AsyncClient):
    payload = {
        "email": "citizen1@safezone.org",
        "password": "Password123!",
        "full_name": "Citizen User",
        "phone_number": "9876543210"
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "citizen1@safezone.org"
    assert data["full_name"] == "Citizen User"
    assert data["role"] == "CITIZEN"
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_duplicate_registration_fails(async_client: AsyncClient):
    payload = {
        "email": "duplicate@safezone.org",
        "password": "Password123!",
        "full_name": "Original User"
    }
    # First registration
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with same email
    res2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    # Register citizen
    reg_payload = {
        "email": "login_test@safezone.org",
        "password": "ValidPassword123",
        "full_name": "Login Test User"
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login_test@safezone.org",
        "password": "ValidPassword123"
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "login_test@safezone.org"
    assert data["user"]["role"] == "CITIZEN"


@pytest.mark.asyncio
async def test_login_invalid_password(async_client: AsyncClient):
    reg_payload = {
        "email": "wrong_pwd@safezone.org",
        "password": "ValidPassword123",
        "full_name": "Wrong Pwd User"
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    login_payload = {
        "email": "wrong_pwd@safezone.org",
        "password": "WrongPassword!"
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client: AsyncClient):
    login_payload = {
        "email": "nobody@safezone.org",
        "password": "SomePassword123"
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_account_rejection(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal

    # Manually create inactive user
    async with TestAsyncSessionLocal() as session:
        inactive_user = User(
            email="inactive@safezone.org",
            hashed_password=get_password_hash("InactivePwd123"),
            full_name="Inactive User",
            role=UserRole.CITIZEN,
            is_active=False
        )
        session.add(inactive_user)
        await session.commit()

    # Attempt login
    login_payload = {
        "email": "inactive@safezone.org",
        "password": "InactivePwd123"
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_current_user_profile(async_client: AsyncClient):
    # Register & Login
    reg_payload = {
        "email": "profile_test@safezone.org",
        "password": "Password123!",
        "full_name": "Profile User"
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    login_res = await async_client.post("/api/v1/auth/login", json={
        "email": "profile_test@safezone.org",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]

    # Call /auth/me with Bearer token
    headers = {"Authorization": f"Bearer {token}"}
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["email"] == "profile_test@safezone.org"
    assert data["full_name"] == "Profile User"
    assert data["role"] == "CITIZEN"


@pytest.mark.asyncio
async def test_get_current_user_unauthorized(async_client: AsyncClient):
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_role_restrictions(async_client: AsyncClient):
    from tests.conftest import TestAsyncSessionLocal

    # Create users with CITIZEN, POLICE, ADMIN roles
    async with TestAsyncSessionLocal() as session:
        citizen_user = User(
            email="citizen_role@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Citizen Role",
            role=UserRole.CITIZEN,
            is_active=True
        )
        police_user = User(
            email="police_role@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Police Role",
            role=UserRole.POLICE,
            is_active=True
        )
        admin_user = User(
            email="admin_role@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Admin Role",
            role=UserRole.ADMIN,
            is_active=True
        )
        session.add_all([citizen_user, police_user, admin_user])
        await session.commit()

    # Generate JWT tokens for each
    citizen_token = create_access_token({"sub": str(citizen_user.id), "email": citizen_user.email, "role": "CITIZEN"})
    police_token = create_access_token({"sub": str(police_user.id), "email": police_user.email, "role": "POLICE"})
    admin_token = create_access_token({"sub": str(admin_user.id), "email": admin_user.email, "role": "ADMIN"})

    # 1. Citizen calling Admin endpoint -> 403 Forbidden
    res = await async_client.get("/api/v1/admin/secure-check", headers={"Authorization": f"Bearer {citizen_token}"})
    assert res.status_code == 403

    # 2. Citizen calling Police endpoint -> 403 Forbidden
    res = await async_client.get("/api/v1/patrols/secure-check", headers={"Authorization": f"Bearer {citizen_token}"})
    assert res.status_code == 403

    # 3. Police calling Admin endpoint -> 403 Forbidden
    res = await async_client.get("/api/v1/admin/secure-check", headers={"Authorization": f"Bearer {police_token}"})
    assert res.status_code == 403

    # 4. Police calling Police endpoint -> 200 OK
    res = await async_client.get("/api/v1/patrols/secure-check", headers={"Authorization": f"Bearer {police_token}"})
    assert res.status_code == 200
    assert res.json()["message"] == "Police authorization verified"

    # 5. Admin calling Admin endpoint -> 200 OK
    res = await async_client.get("/api/v1/admin/secure-check", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["message"] == "Admin authorization verified"
