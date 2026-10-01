"""SafeZone Live WebSocket Connection and Telemetry Streaming Manager.

Provides real-time pub/sub synchronization ONLY for active SOS distress alerts:
- Citizen subscribers receive strictly privacy-safe status progression & approximate distance
- Police & Admin subscribers receive operational location telemetry and officer coordinates
- Automatic graceful disconnection handling
- Zero impact on standard REST CRUD operations.
"""

import json
from typing import Dict, List, Tuple, Optional, Any
from fastapi import WebSocket
from app.core.logging import logger


class LiveSOSManager:
    _instance: Optional["LiveSOSManager"] = None

    def __init__(self):
        # Maps sos_id -> list of (websocket, role, user_id)
        self._connections: Dict[int, List[Tuple[WebSocket, str, Optional[int]]]] = {}

    @classmethod
    def get_instance(cls) -> "LiveSOSManager":
        if cls._instance is None:
            cls._instance = LiveSOSManager()
        return cls._instance

    async def connect(self, websocket: WebSocket, sos_id: int, role: str = "citizen", user_id: Optional[int] = None):
        """Register and accept an active WebSocket connection for an SOS emergency."""
        await websocket.accept()
        if sos_id not in self._connections:
            self._connections[sos_id] = []
        self._connections[sos_id].append((websocket, role.lower(), user_id))
        logger.info(f"[LiveSOSManager] Client connected to SOS #{sos_id} (Role: {role}, User: {user_id}). Active: {len(self._connections[sos_id])}")

    def disconnect(self, websocket: WebSocket, sos_id: int):
        """Remove a disconnected WebSocket client."""
        if sos_id in self._connections:
            self._connections[sos_id] = [conn for conn in self._connections[sos_id] if conn[0] != websocket]
            if not self._connections[sos_id]:
                del self._connections[sos_id]
            logger.info(f"[LiveSOSManager] Client disconnected from SOS #{sos_id}.")

    async def broadcast_status_update(
        self,
        sos_id: int,
        status: str,
        approximate_distance_km: Optional[float] = None,
        estimated_arrival_minutes: Optional[int] = None,
        operational_details: Optional[Dict[str, Any]] = None,
    ):
        """Broadcast status update to all connected clients with role-based privacy segregation."""
        if sos_id not in self._connections:
            return

        # 1. Citizen Privacy-Safe Payload
        # Strictly excludes raw police coordinates, PRP details, and internal risk metrics
        citizen_payload = {
            "type": "SOS_STATUS_UPDATE",
            "sos_id": sos_id,
            "status": status,
            "approximate_distance_km": approximate_distance_km,
            "estimated_arrival_minutes": estimated_arrival_minutes,
            "timestamp": operational_details.get("timestamp") if operational_details else None,
        }

        # 2. Police / Admin Operational Payload
        police_payload = {
            "type": "SOS_STATUS_UPDATE",
            "sos_id": sos_id,
            "status": status,
            "approximate_distance_km": approximate_distance_km,
            "estimated_arrival_minutes": estimated_arrival_minutes,
            "operational": operational_details or {},
        }

        dead_connections = []
        for ws, role, user_id in self._connections.get(sos_id, []):
            try:
                if role in ("police", "admin"):
                    await ws.send_text(json.dumps(police_payload))
                else:
                    await ws.send_text(json.dumps(citizen_payload))
            except Exception as e:
                logger.warning(f"[LiveSOSManager] Failed sending live update to client for SOS #{sos_id}: {e}")
                dead_connections.append((ws, role, user_id))

        # Clean up dead sockets
        for dead in dead_connections:
            self.disconnect(dead[0], sos_id)

    async def broadcast_location_telemetry(
        self,
        sos_id: int,
        approximate_distance_km: Optional[float],
        police_latitude: float,
        police_longitude: float,
    ):
        """Broadcast location update during active pursuit / response."""
        if sos_id not in self._connections:
            return

        citizen_payload = {
            "type": "LOCATION_TELEMETRY",
            "sos_id": sos_id,
            "approximate_distance_km": approximate_distance_km,
        }

        police_payload = {
            "type": "LOCATION_TELEMETRY",
            "sos_id": sos_id,
            "approximate_distance_km": approximate_distance_km,
            "police_latitude": police_latitude,
            "police_longitude": police_longitude,
        }

        dead_connections = []
        for ws, role, user_id in self._connections.get(sos_id, []):
            try:
                if role in ("police", "admin"):
                    await ws.send_text(json.dumps(police_payload))
                else:
                    await ws.send_text(json.dumps(citizen_payload))
            except Exception:
                dead_connections.append((ws, role, user_id))

        for dead in dead_connections:
            self.disconnect(dead[0], sos_id)


live_sos_manager = LiveSOSManager.get_instance()
