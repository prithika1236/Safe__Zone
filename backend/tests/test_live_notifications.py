import pytest
import json
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserRole, EmergencyContact
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.sos import SOSRequest
from app.core.security import create_access_token, get_password_hash
from app.services.live_manager import LiveSOSManager, live_sos_manager
from app.services.notification_service import NotificationService, notification_service
from app.services.dispatch_service import dispatch_service


@pytest.mark.asyncio
async def test_live_manager_role_segregation():
    """Verify LiveSOSManager segregates citizen privacy vs police/admin operational telemetry."""
    manager = LiveSOSManager()

    # Mock WebSockets for Citizen and Police
    citizen_ws = AsyncMock()
    police_ws = AsyncMock()

    await manager.connect(citizen_ws, sos_id=99, role="citizen", user_id=1)
    await manager.connect(police_ws, sos_id=99, role="police", user_id=2)

    # Broadcast status update
    await manager.broadcast_status_update(
        sos_id=99,
        status="EN_ROUTE",
        approximate_distance_km=2.4,
        estimated_arrival_minutes=5,
        operational_details={
            "patrol_unit_id": 10,
            "officer_id": 2,
            "police_latitude": 13.0850,
            "police_longitude": 80.2750,
        },
    )

    # Citizen WebSocket must have received privacy-safe payload
    assert citizen_ws.send_text.called
    citizen_sent = json.loads(citizen_ws.send_text.call_args[0][0])
    assert citizen_sent["status"] == "EN_ROUTE"
    assert citizen_sent["approximate_distance_km"] == 2.4
    assert citizen_sent["estimated_arrival_minutes"] == 5
    # Strict privacy: NO raw police coordinates or operational internals
    assert "operational" not in citizen_sent
    assert "police_latitude" not in citizen_sent

    # Police WebSocket must have received full operational payload
    assert police_ws.send_text.called
    police_sent = json.loads(police_ws.send_text.call_args[0][0])
    assert police_sent["status"] == "EN_ROUTE"
    assert "operational" in police_sent
    assert police_sent["operational"]["police_latitude"] == 13.0850

    # Disconnect citizen
    manager.disconnect(citizen_ws, sos_id=99)
    assert len(manager._connections[99]) == 1


@pytest.mark.asyncio
async def test_live_location_telemetry_segregation():
    """Verify live location telemetry segregates coordinates from citizen payload."""
    manager = LiveSOSManager()

    citizen_ws = AsyncMock()
    police_ws = AsyncMock()

    await manager.connect(citizen_ws, sos_id=101, role="citizen")
    await manager.connect(police_ws, sos_id=101, role="police")

    await manager.broadcast_location_telemetry(
        sos_id=101,
        approximate_distance_km=1.8,
        police_latitude=13.0840,
        police_longitude=80.2730,
    )

    citizen_sent = json.loads(citizen_ws.send_text.call_args[0][0])
    assert citizen_sent["type"] == "LOCATION_TELEMETRY"
    assert citizen_sent["approximate_distance_km"] == 1.8
    assert "police_latitude" not in citizen_sent

    police_sent = json.loads(police_ws.send_text.call_args[0][0])
    assert police_sent["type"] == "LOCATION_TELEMETRY"
    assert police_sent["police_latitude"] == 13.0840
    assert police_sent["police_longitude"] == 80.2730


@pytest.mark.asyncio
async def test_notification_service_emergency_sms_and_fallbacks(async_client):
    """Test NotificationService SMS dispatch, in-app dev fallback, and error handling."""
    from app.database.session import get_async_db
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as db:
        # Create citizen with primary emergency contact
        citizen = User(
            email="citizen.notify@safezone.org",
            hashed_password=get_password_hash("Secret123!"),
            full_name="Citizen Notification Test",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(citizen)
        await db.flush()

        contact = EmergencyContact(
            user_id=citizen.id,
            name="Emergency Contact Person",
            phone_number="+919876543210",
            relationship_type="Parent",
            is_primary=True,
        )
        db.add(contact)
        await db.flush()

        sos = SOSRequest(
            citizen_id=citizen.id,
            latitude=13.0827,
            longitude=80.2707,
            status="PENDING",
        )
        db.add(sos)
        await db.commit()
        await db.refresh(sos)

        service = NotificationService()

        # 1. Test SMS dispatch
        sms_res = await service.send_emergency_contact_sms(db, citizen, sos)
        assert sms_res["status"] in ("NOT_CONFIGURED", "DELIVERED")
        assert sms_res["recipient_name"] == "Emergency Contact Person"
        assert "maps.google.com" in sms_res["message"]

        # Duplicate SMS should skip
        dup_res = await service.send_emergency_contact_sms(db, citizen, sos)
        assert dup_res["status"] == "ALREADY_SENT"

        # 2. Test Police Notification (Dev In-App fallback)
        police_notif = await service.notify_police_new_sos(db, sos, officer_id=5)
        assert police_notif["status"] in ("NOT_CONFIGURED", "DELIVERED")
        assert police_notif["sos_id"] == sos.id

        # 3. Test Citizen Status Notification
        citizen_notif = await service.notify_citizen_status_update(db, sos, new_status="EN_ROUTE", approximate_distance_km=2.1)
        assert citizen_notif["status"] in ("NOT_CONFIGURED", "DELIVERED")
        assert citizen_notif["new_status"] == "EN_ROUTE"
        assert "payload" in citizen_notif
        assert "police_latitude" not in citizen_notif["payload"]


def test_websocket_sos_endpoint(client: TestClient):
    """Test FastAPI WebSocket connection to /api/v1/sos/ws/{sos_id} and ping/pong."""
    with client.websocket_connect("/api/v1/sos/ws/42") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert json.loads(data) == {"type": "pong"}


@pytest.mark.asyncio
async def test_end_to_end_sos_dispatch_broadcast(async_client):
    """End-to-end integration test verifying that creating and transitioning SOS triggers broadcasts without errors."""
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as db:
        # Create Citizen
        citizen = User(
            email="e2e.citizen@safezone.org",
            hashed_password=get_password_hash("CitizenPass123!"),
            full_name="E2E Citizen",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(citizen)

        # Create Police Officer & Patrol Unit
        police_user = User(
            email="e2e.officer@safezone.org",
            hashed_password=get_password_hash("PolicePass123!"),
            full_name="E2E Officer",
            role=UserRole.POLICE,
            is_active=True,
        )
        db.add(police_user)
        await db.flush()

        officer = PoliceOfficer(
            user_id=police_user.id,
            badge_number="E2E-999",
            rank="Inspector",
            station_name="E2E Station",
            on_duty=True,
            is_available=True,
        )
        db.add(officer)

        unit = PatrolUnit(
            unit_code="E2E-PATROL-1",
            unit_type="CAR",
            status="AVAILABLE",
            current_latitude=13.0830,
            current_longitude=80.2710,
        )
        db.add(unit)
        await db.commit()

        citizen_token = create_access_token({"sub": str(citizen.id), "email": citizen.email, "role": "citizen"})
        police_token = create_access_token({"sub": str(police_user.id), "email": police_user.email, "role": "police"})

        # 1. Trigger SOS -> automatically dispatches and broadcasts
        sos_resp = await async_client.post(
            "/api/v1/sos/trigger",
            headers={"Authorization": f"Bearer {citizen_token}"},
            json={"latitude": 13.0827, "longitude": 80.2707, "notes": "E2E Live Test"},
        )
        assert sos_resp.status_code == 201
        sos_data = sos_resp.json()
        sos_id = sos_data["id"]
        assert sos_data["status"] == "ASSIGNED"
        assert sos_data["approximate_distance_km"] is not None

        # 2. Officer accepts dispatch -> transitions to ACCEPTED and broadcasts
        accept_resp = await async_client.post(
            f"/api/v1/sos/{sos_id}/accept",
            headers={"Authorization": f"Bearer {police_token}"},
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "ACCEPTED"

        # 3. Officer records location update -> broadcasts location telemetry
        loc_resp = await async_client.post(
            "/api/v1/patrols/location",
            headers={"Authorization": f"Bearer {police_token}"},
            json={"latitude": 13.0828, "longitude": 80.2708},
        )
        assert loc_resp.status_code == 200

        # 4. Officer transitions status to EN_ROUTE -> ARRIVED -> RESOLVED
        for next_st in ["EN_ROUTE", "ARRIVED", "RESOLVED"]:
            st_resp = await async_client.post(
                f"/api/v1/sos/{sos_id}/status",
                headers={"Authorization": f"Bearer {police_token}"},
                json={"status": next_st},
            )
            assert st_resp.status_code == 200
            assert st_resp.json()["status"] == next_st


@pytest.mark.asyncio
async def test_emergency_sms_scenarios_a_through_f(async_client):
    """Exhaustively verify Emergency SMS Scenarios A through F.
    
    Scenario A: Primary contact selection, formatting, privacy verification (no PRP, no officer, no risk score).
    Scenario B: Citizen with no contacts -> SKIPPED cleanly, non-blocking.
    Scenario C: Citizen with non-primary contacts only -> deterministic fallback without errors.
    Scenario D: Contact with strange/invalid phone format -> handled defensively.
    Scenario E: Simulated provider exception -> returns FAILED, non-blocking.
    Scenario F: Idempotency -> repeated invocations for same SOS ID yield ALREADY_SENT.
    """
    from tests.conftest import TestAsyncSessionLocal
    from unittest.mock import patch

    async with TestAsyncSessionLocal() as db:
        # User A: With Primary & Secondary contacts
        user_a = User(
            email="user.a@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Alice A",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(user_a)
        await db.flush()

        c_sec = EmergencyContact(
            user_id=user_a.id,
            name="Alice Friend",
            phone_number="+919876500001",
            relationship_type="Friend",
            is_primary=False,
        )
        c_pri = EmergencyContact(
            user_id=user_a.id,
            name="Alice Mom",
            phone_number="+919876500002",
            relationship_type="Mother",
            is_primary=True,
        )
        db.add_all([c_sec, c_pri])

        # User B: No contacts
        user_b = User(
            email="user.b@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Bob B",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(user_b)
        await db.flush()

        # User C: Non-primary contacts only
        user_c = User(
            email="user.c@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Charlie C",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(user_c)
        await db.flush()

        c_np1 = EmergencyContact(
            user_id=user_c.id,
            name="Charlie Colleague",
            phone_number="+919876500003",
            relationship_type="Colleague",
            is_primary=False,
        )
        db.add(c_np1)

        # SOS records
        sos_a = SOSRequest(citizen_id=user_a.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        sos_b = SOSRequest(citizen_id=user_b.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        sos_c = SOSRequest(citizen_id=user_c.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        sos_d = SOSRequest(citizen_id=user_a.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        db.add_all([sos_a, sos_b, sos_c, sos_d])
        await db.commit()
        await db.refresh(sos_a)
        await db.refresh(sos_b)
        await db.refresh(sos_c)
        await db.refresh(sos_d)

        service = NotificationService()

        # --- SCENARIO A: Primary Contact Selection & Privacy Check ---
        res_a = await service.send_emergency_contact_sms(db, user_a, sos_a)
        assert res_a["status"] in ("NOT_CONFIGURED", "DELIVERED", "SENT")
        assert res_a["recipient_name"] == "Alice Mom"
        assert res_a["recipient_phone"] == "+919876500002"
        assert res_a["is_primary"] is True
        # Privacy guarantees
        assert "maps.google.com" in res_a["message"]
        assert "Alice A" in res_a["message"]
        assert "prp" not in res_a["message"].lower()
        assert "officer" not in res_a["message"].lower()
        assert "patrol" not in res_a["message"].lower()
        assert "risk" not in res_a["message"].lower()

        # --- SCENARIO B: Citizen with No Registered Contacts ---
        res_b = await service.send_emergency_contact_sms(db, user_b, sos_b)
        assert res_b["status"] == "SKIPPED"
        assert res_b["reason"] == "NO_CONTACTS"

        # --- SCENARIO C: Contacts Exist But NONE Marked Primary (Strictly Skipped) ---
        res_c = await service.send_emergency_contact_sms(db, user_c, sos_c)
        assert res_c["status"] == "SKIPPED"
        assert res_c["reason"] == "NO_PRIMARY_CONTACT"

        # --- SCENARIO D: Primary Contact with invalid phone format ---
        c_pri.phone_number = "123-INVALID-PHONE"
        await db.commit()
        res_d = await service.send_emergency_contact_sms(db, user_a, sos_d)
        assert res_d["status"] == "FAILED"
        assert res_d["reason"] == "INVALID_PHONE_NUMBER"

        # --- SCENARIO E: Simulated Provider / Internal Exception ---
        sos_e = SOSRequest(citizen_id=user_a.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        db.add(sos_e)
        await db.commit()
        await db.refresh(sos_e)

        # Force exception inside query
        with patch.object(db, "execute", side_effect=RuntimeError("Simulated DB / Network Failure")):
            res_e = await service.send_emergency_contact_sms(db, user_a, sos_e)
            assert res_e["status"] == "FAILED"
            assert "Simulated DB / Network Failure" in res_e["error"]

        # --- SCENARIO F: Idempotency & Polling Duplicate Protection ---
        # Calling again on sos_a which was already sent in Scenario A
        res_f = await service.send_emergency_contact_sms(db, user_a, sos_a)
        assert res_f["status"] == "ALREADY_SENT"
        assert res_f["sos_id"] == sos_a.id


@pytest.mark.asyncio
async def test_twilio_phone_normalization_and_e164_formatting():
    """Verify phone number normalization rules to Twilio-compatible E.164 format."""
    norm = NotificationService.normalize_phone_number

    # 1. Standard 10-digit Indian numbers -> +91
    assert norm("9840012345") == "+919840012345"
    assert norm("98400 12345") == "+919840012345"
    assert norm("98400-12345") == "+919840012345"
    assert norm("(984) 001-2345") == "+919840012345"

    # 2. Already +91 prefixed
    assert norm("+919840012345") == "+919840012345"
    assert norm("+91 98400 12345") == "+919840012345"

    # 3. 11-digit leading 0 format
    assert norm("09840012345") == "+919840012345"

    # 4. 12-digit 91 format
    assert norm("919840012345") == "+919840012345"

    # 5. International general format with +
    assert norm("+14155552671") == "+14155552671"
    assert norm("0014155552671") == "+14155552671"

    # 6. Invalid numbers
    assert norm(None) is None
    assert norm("") is None
    assert norm("123") is None
    assert norm("abcdefghij") is None
    assert norm("+91invalid123") is None


@pytest.mark.asyncio
async def test_twilio_mocked_dispatch_trial_and_production_modes():
    """Verify Twilio SMS dispatch under mocked Trial and Production modes without sending real SMS."""
    from tests.conftest import TestAsyncSessionLocal
    from unittest.mock import MagicMock, patch
    from app.core.config import settings

    async with TestAsyncSessionLocal() as db:
        user = User(
            email="twilio.test@safezone.org",
            hashed_password=get_password_hash("Pass123!"),
            full_name="Twilio Test Citizen",
            role=UserRole.CITIZEN,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        contact = EmergencyContact(
            user_id=user.id,
            name="Twilio Primary",
            phone_number="9840099999",  # 10-digit format
            relationship_type="Parent",
            is_primary=True,
        )
        db.add(contact)

        sos_trial = SOSRequest(citizen_id=user.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        sos_prod = SOSRequest(citizen_id=user.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        sos_fail = SOSRequest(citizen_id=user.id, latitude=13.0827, longitude=80.2707, status="PENDING")
        db.add_all([sos_trial, sos_prod, sos_fail])
        await db.commit()
        await db.refresh(sos_trial)
        await db.refresh(sos_prod)
        await db.refresh(sos_fail)

        service = NotificationService()

        # Mock Twilio Client message creation
        mock_msg = MagicMock()
        mock_msg.sid = "SM_MOCK_1234567890abcdef"
        mock_msg.status = "queued"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg

        # 1. Trial Mode Dispatch
        with patch.object(settings, "TWILIO_ACCOUNT_SID", "AC_mock_sid"), \
             patch.object(settings, "TWILIO_AUTH_TOKEN", "mock_auth_token"), \
             patch.object(settings, "TWILIO_PHONE_NUMBER", "+15005550006"), \
             patch.object(settings, "TWILIO_TRIAL_MODE", True), \
             patch.object(settings, "TWILIO_TRIAL_TEMPLATE", "sms_account_alerts"), \
             patch.object(service, "_get_twilio_client", return_value=mock_client):

            res_trial = await service.send_emergency_contact_sms(db, user, sos_trial)
            assert res_trial["status"] == "SENT"
            assert res_trial["provider"] == "TWILIO"
            assert res_trial["message_sid"] == "SM_MOCK_1234567890abcdef"
            assert res_trial["trial_mode"] is True
            assert res_trial["recipient_phone"] == "+919840099999"  # E.164 normalized
            assert res_trial["message"] == "sms_account_alerts"
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["to"] == "+919840099999"
            assert call_kwargs["from_"] == "+15005550006"
            assert call_kwargs["body"] == "sms_account_alerts"
            assert "SafeZone Emergency Alert" not in call_kwargs["body"]

        mock_client.messages.create.reset_mock()

        # 2. Production Mode Dispatch
        with patch.object(settings, "TWILIO_ACCOUNT_SID", "AC_mock_sid"), \
             patch.object(settings, "TWILIO_AUTH_TOKEN", "mock_auth_token"), \
             patch.object(settings, "TWILIO_PHONE_NUMBER", "+15005550006"), \
             patch.object(settings, "TWILIO_TRIAL_MODE", False), \
             patch.object(service, "_get_twilio_client", return_value=mock_client):

            res_prod = await service.send_emergency_contact_sms(db, user, sos_prod)
            assert res_prod["status"] == "SENT"
            assert res_prod["provider"] == "TWILIO"
            assert res_prod["trial_mode"] is False
            assert "SafeZone Emergency Alert" in res_prod["message"]
            assert res_prod["recipient_phone"] == "+919840099999"
            mock_client.messages.create.assert_called_once()
            call_kwargs_prod = mock_client.messages.create.call_args.kwargs
            assert call_kwargs_prod["to"] == "+919840099999"
            assert call_kwargs_prod["from_"] == "+15005550006"
            assert "SafeZone Emergency Alert" in call_kwargs_prod["body"]
            assert call_kwargs_prod["body"] != "sms_account_alerts"

        # 3. Provider Error Handling (e.g. Unverified Number in Trial or Network Error)
        mock_client.messages.create.side_effect = RuntimeError("Twilio Error 21608: The number is unverified.")
        with patch.object(settings, "TWILIO_ACCOUNT_SID", "AC_mock_sid"), \
             patch.object(settings, "TWILIO_AUTH_TOKEN", "mock_auth_token"), \
             patch.object(settings, "TWILIO_PHONE_NUMBER", "+15005550006"), \
             patch.object(service, "_get_twilio_client", return_value=mock_client):

            res_fail = await service.send_emergency_contact_sms(db, user, sos_fail)
            assert res_fail["status"] == "FAILED"
            assert res_fail["provider"] == "TWILIO"
            assert "21608" in res_fail["error"]



