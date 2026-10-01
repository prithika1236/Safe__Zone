import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.user import User, EmergencyContact
from app.models.sos import SOSRequest
from app.core.config import settings
from app.core.logging import logger


class NotificationService:
    _instance: Optional["NotificationService"] = None

    def __init__(self):
        # Set of SOS IDs that have already triggered an emergency SMS notification
        self._notified_sos_ids: Set[int] = set()
        self._firebase_initialized: bool = False

    @classmethod
    def get_instance(cls) -> "NotificationService":
        if cls._instance is None:
            cls._instance = NotificationService()
        return cls._instance

    @staticmethod
    def normalize_phone_number(raw_phone: Optional[str]) -> Optional[str]:
        """Normalize phone numbers to Twilio-compatible E.164 format.
        
        Rules:
        - None or empty string -> None
        - Strips whitespace, dashes, periods, parentheses
        - If starts with '+', validates digits (10-15 digits total) and preserves
        - If 10 digits (standard Indian mobile format), prefixes with '+91'
        - If 11 digits starting with '0', strips leading 0 and prefixes with '+91'
        - If 12 digits starting with '91', prefixes with '+'
        - Invalid format/length -> None
        """
        if not raw_phone:
            return None
        
        cleaned = re.sub(r"[\s\-\(\)\.]", "", str(raw_phone).strip())
        if not cleaned:
            return None

        # Already starts with '+'
        if cleaned.startswith("+"):
            digits = cleaned[1:]
            if digits.isdigit() and 10 <= len(digits) <= 15:
                return cleaned
            return None

        # International '00' prefix
        if cleaned.startswith("00") and len(cleaned) > 12:
            digits = cleaned[2:]
            if digits.isdigit() and 10 <= len(digits) <= 15:
                return f"+{digits}"

        # Standard 10-digit mobile number (e.g., 9840011111)
        if len(cleaned) == 10 and cleaned.isdigit():
            return f"+91{cleaned}"

        # 11-digit mobile starting with 0 (e.g., 09840011111)
        if len(cleaned) == 11 and cleaned.startswith("0") and cleaned[1:].isdigit():
            return f"+91{cleaned[1:]}"

        # 12-digit Indian number starting with 91 (e.g., 919840011111)
        if len(cleaned) == 12 and cleaned.startswith("91") and cleaned.isdigit():
            return f"+{cleaned}"

        # General E.164 digits without '+' (11-15 digits)
        if 11 <= len(cleaned) <= 15 and cleaned.isdigit():
            return f"+{cleaned}"

        return None

    def _get_twilio_client(self):
        """Safely initialize Twilio REST Client using environment credentials."""
        account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
        auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
        if not account_sid or not auth_token:
            return None
        try:
            from twilio.rest import Client
            return Client(account_sid, auth_token)
        except Exception as e:
            logger.warning(f"[NotificationService] Failed to initialize Twilio client: {e}")
            return None

    def _init_firebase_if_configured(self) -> bool:
        """Attempt to initialize Firebase Admin SDK safely if credentials are provided in settings."""
        if self._firebase_initialized:
            return True

        cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")
        if not cred_path or not os.path.exists(cred_path):
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials

            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            self._firebase_initialized = True
            logger.info("[NotificationService] Firebase Admin SDK initialized successfully.")
            return True
        except Exception as e:
            logger.warning(f"[NotificationService] Firebase Admin SDK initialization failed: {e}")
            return False

    async def send_emergency_contact_sms(
        self,
        db: AsyncSession,
        citizen: User,
        sos: SOSRequest,
    ) -> Dict[str, Any]:
        """Trigger emergency SMS notification to citizen's primary emergency contact via Twilio.
        
        Guaranteed to be non-blocking and safe: failures, unverified trial numbers,
        or missing providers will never raise unhandled exceptions or interrupt SOS dispatch.
        """
        if sos.id in self._notified_sos_ids:
            logger.info(f"[NotificationService] SOS #{sos.id} already triggered SMS notification. Skipping duplicate.")
            return {"status": "ALREADY_SENT", "sos_id": sos.id}

        try:
            # 1. Fetch citizen's emergency contacts (strict primary contact enforcement)
            stmt = (
                select(EmergencyContact)
                .where(EmergencyContact.user_id == citizen.id)
                .order_by(EmergencyContact.is_primary.desc(), EmergencyContact.id.asc())
            )
            res = await db.execute(stmt)
            contacts = res.scalars().all()

            if not contacts:
                logger.info(f"[NotificationService] Citizen #{citizen.id} has no registered emergency contacts.")
                return {
                    "status": "SKIPPED",
                    "reason": "NO_CONTACTS",
                    "sos_id": sos.id,
                }

            primary_contacts = [c for c in contacts if c.is_primary]
            if not primary_contacts:
                logger.info(f"[NotificationService] Citizen #{citizen.id} has registered emergency contacts but none marked as primary.")
                return {
                    "status": "SKIPPED",
                    "reason": "NO_PRIMARY_CONTACT",
                    "sos_id": sos.id,
                }

            primary_contact = primary_contacts[0]

            # 2. Normalize recipient phone number to E.164
            normalized_phone = self.normalize_phone_number(primary_contact.phone_number)
            if not normalized_phone:
                logger.warning(f"[NotificationService] Invalid phone number format '{primary_contact.phone_number}' for contact #{primary_contact.id}.")
                self._notified_sos_ids.add(sos.id)
                return {
                    "status": "FAILED",
                    "reason": "INVALID_PHONE_NUMBER",
                    "recipient_name": primary_contact.name,
                    "recipient_phone": primary_contact.phone_number,
                    "sos_id": sos.id,
                }

            # 3. Format Privacy-Safe SMS payload
            citizen_name = getattr(citizen, "full_name", None) or "Citizen"
            triggered_str = (
                sos.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if sos.triggered_at
                else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            location_link = f"https://maps.google.com/?q={sos.latitude:.6f},{sos.longitude:.6f}"
            
            sms_text = (
                f"SafeZone Emergency Alert: An SOS distress call was triggered by your contact "
                f"{citizen_name}. Time: {triggered_str}. "
                f"Emergency Location: {location_link}"
            )

            # 4. Twilio Dispatch Execution Boundary
            twilio_client = self._get_twilio_client()
            from_phone = getattr(settings, "TWILIO_PHONE_NUMBER", "")
            trial_mode = getattr(settings, "TWILIO_TRIAL_MODE", False)
            trial_template = getattr(settings, "TWILIO_TRIAL_TEMPLATE", "sms_account_alerts")

            if twilio_client and from_phone:
                if trial_mode:
                    logger.info(
                        f"[NotificationService][TWILIO_TRIAL_MODE] Sending SMS via Twilio Trial Mode "
                        f"(Template: {trial_template}) to recipient: {primary_contact.name} ({normalized_phone})"
                    )
                    msg_body = trial_template
                else:
                    logger.info(
                        f"[NotificationService][TWILIO_PRODUCTION] Sending SafeZone Emergency SMS to "
                        f"recipient: {primary_contact.name} ({normalized_phone})"
                    )
                    msg_body = sms_text

                try:
                    twilio_message = twilio_client.messages.create(
                        body=msg_body,
                        from_=from_phone,
                        to=normalized_phone,
                    )
                    
                    self._notified_sos_ids.add(sos.id)
                    logger.info(
                        f"[NotificationService] Twilio SMS accepted by provider. "
                        f"SID: {twilio_message.sid}, Status: {getattr(twilio_message, 'status', 'accepted')}"
                    )
                    
                    return {
                        "status": "SENT",
                        "provider": "TWILIO",
                        "message_sid": twilio_message.sid,
                        "provider_status": getattr(twilio_message, "status", "accepted"),
                        "trial_mode": trial_mode,
                        "recipient_name": primary_contact.name,
                        "recipient_phone": normalized_phone,
                        "is_primary": primary_contact.is_primary,
                        "message": msg_body,
                        "sos_id": sos.id,
                    }
                except Exception as twilio_err:
                    logger.error(f"[NotificationService] Twilio API dispatch error for SOS #{sos.id}: {str(twilio_err)}")
                    self._notified_sos_ids.add(sos.id)
                    return {
                        "status": "FAILED",
                        "provider": "TWILIO",
                        "error": str(twilio_err),
                        "recipient_name": primary_contact.name,
                        "recipient_phone": normalized_phone,
                        "is_primary": primary_contact.is_primary,
                        "sos_id": sos.id,
                    }
            else:
                # Unconfigured Twilio environment fallback
                logger.info(
                    f"[NotificationService][DEV_FALLBACK] Twilio not configured. "
                    f"Simulated SMS -> Recipient: {primary_contact.name} ({normalized_phone}), "
                    f"Relationship: {primary_contact.relationship_type}. Content: \"{sms_text}\""
                )
                self._notified_sos_ids.add(sos.id)
                return {
                    "status": "NOT_CONFIGURED",
                    "provider": "TWILIO",
                    "recipient_name": primary_contact.name,
                    "recipient_phone": normalized_phone,
                    "is_primary": primary_contact.is_primary,
                    "message": sms_text,
                    "sos_id": sos.id,
                }

        except Exception as e:
            logger.error(f"[NotificationService] Error in emergency SMS dispatch for SOS #{sos.id}: {str(e)}")
            return {
                "status": "FAILED",
                "error": str(e),
                "sos_id": sos.id,
            }

    async def notify_police_new_sos(
        self,
        db: AsyncSession,
        sos: SOSRequest,
        officer_id: Optional[int],
    ) -> Dict[str, Any]:
        """Notify assigned Police Officer about incoming SOS emergency dispatch."""
        try:
            payload = {
                "type": "NEW_SOS_DISPATCH",
                "sos_id": sos.id,
                "latitude": sos.latitude,
                "longitude": sos.longitude,
                "status": sos.status,
                "notes": sos.notes,
                "triggered_at": sos.triggered_at.isoformat() if sos.triggered_at else datetime.utcnow().isoformat(),
            }

            if self._init_firebase_if_configured():
                try:
                    from firebase_admin import messaging

                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=f"URGENT: SOS Dispatch #{sos.id}",
                            body=f"Emergency distress call assigned. Location: {sos.latitude:.4f}, {sos.longitude:.4f}",
                        ),
                        data={k: str(v) for k, v in payload.items() if v is not None},
                        topic=f"officer_{officer_id}" if officer_id else "police_dispatch",
                    )
                    response = messaging.send(message)
                    logger.info(f"[NotificationService] FCM Police dispatch notification sent: {response}")
                    return {"status": "DELIVERED", "channel": "FCM", "message_id": response, "sos_id": sos.id}
                except Exception as fcm_err:
                    logger.warning(f"[NotificationService] FCM dispatch failed: {fcm_err}. Using dev in-app fallback.")

            logger.info(f"[NotificationService][DEV_FALLBACK] In-App Police Notification -> Officer #{officer_id} for SOS #{sos.id} (Status: {sos.status})")
            return {
                "status": "NOT_CONFIGURED",
                "channel": "DEV_IN_APP",
                "recipient_officer_id": officer_id,
                "sos_id": sos.id,
                "payload": payload,
            }

        except Exception as e:
            logger.error(f"[NotificationService] Error sending police notification for SOS #{sos.id}: {e}")
            return {"status": "FAILED", "error": str(e), "sos_id": sos.id}

    async def notify_citizen_status_update(
        self,
        db: AsyncSession,
        sos: SOSRequest,
        new_status: str,
        approximate_distance_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Notify Citizen about response status update with strict privacy segregation."""
        try:
            # Strictly privacy-safe payload: NO raw officer GPS, NO PRP, NO risk score
            status_messages = {
                "ASSIGNED": "A police patrol unit has been assigned to your emergency.",
                "ACCEPTED": "The assigned officer has acknowledged your distress alert and is preparing to respond.",
                "EN_ROUTE": "Police patrol is en route to your location.",
                "ARRIVED": "The responder has arrived at your emergency location.",
                "RESOLVED": "Your emergency incident has been resolved. Stay safe.",
                "NO_AVAILABLE_PATROL": "High emergency load: central command has escalated your distress call.",
            }

            message_text = status_messages.get(new_status.upper(), f"SOS update: {new_status}")
            if approximate_distance_km is not None and new_status.upper() in ("ASSIGNED", "ACCEPTED", "EN_ROUTE"):
                message_text += f" Approximate distance: ~{approximate_distance_km:.1f} km."

            payload = {
                "type": "SOS_STATUS_UPDATE",
                "sos_id": sos.id,
                "status": new_status,
                "approximate_distance_km": approximate_distance_km,
                "message": message_text,
            }

            if self._init_firebase_if_configured():
                try:
                    from firebase_admin import messaging

                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=f"SafeZone Alert: {new_status}",
                            body=message_text,
                        ),
                        data={k: str(v) for k, v in payload.items() if v is not None},
                        topic=f"citizen_{sos.citizen_id}",
                    )
                    response = messaging.send(message)
                    logger.info(f"[NotificationService] FCM Citizen notification sent: {response}")
                    return {"status": "DELIVERED", "channel": "FCM", "message_id": response, "sos_id": sos.id}
                except Exception as fcm_err:
                    logger.warning(f"[NotificationService] FCM Citizen notification failed: {fcm_err}. Using dev in-app fallback.")

            logger.info(f"[NotificationService][DEV_FALLBACK] In-App Citizen Notification -> Citizen #{sos.citizen_id} for SOS #{sos.id} (Status: {new_status})")
            return {
                "status": "NOT_CONFIGURED",
                "channel": "DEV_IN_APP",
                "citizen_id": sos.citizen_id,
                "sos_id": sos.id,
                "new_status": new_status,
                "payload": payload,
            }

        except Exception as e:
            logger.error(f"[NotificationService] Error sending citizen status notification for SOS #{sos.id}: {e}")
            return {"status": "FAILED", "error": str(e), "sos_id": sos.id}


notification_service = NotificationService.get_instance()

