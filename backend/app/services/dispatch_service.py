"""SafeZone Real-Time Emergency SOS Dispatch Service.

Implements the end-to-end emergency response workflow:
- Real-time matching with nearest eligible, on-duty, available police patrols
- Concurrency control and transactional reservation preventing duplicate assignments
- Strict status transition state machine (PENDING -> ASSIGNED -> ACCEPTED -> EN_ROUTE -> ARRIVED -> RESOLVED)
- Explicit NO_AVAILABLE_PATROL handling
- Officer decline and loop-free redispatch to next eligible patrol
- Automatic emergency contact SMS notification triggers (non-blocking)
- Patrol resource release upon emergency resolution
- Strategic citizen privacy guarantee (zero PRP or raw police GPS leakage).
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.police import PoliceOfficer, PatrolUnit
from app.models.sos import SOSRequest
from app.models.optimization import PatrolAssignment
from app.services.location_service import LocationService
from app.services.notification_service import notification_service
from app.services.live_manager import live_sos_manager
from app.core.logging import logger



class DispatchService:
    _instance: Optional["DispatchService"] = None

    # Canonical status state machine transitions
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "PENDING": {"ASSIGNED", "ACCEPTED", "NO_AVAILABLE_PATROL", "CANCELLED"},
        "SUBMITTED": {"ASSIGNED", "ACCEPTED", "NO_AVAILABLE_PATROL", "CANCELLED"},
        "ACTIVE": {"ASSIGNED", "ACCEPTED", "NO_AVAILABLE_PATROL", "CANCELLED"},
        "ASSIGNED": {"ACCEPTED", "NO_AVAILABLE_PATROL", "CANCELLED"},
        "ACCEPTED": {"EN_ROUTE", "CANCELLED"},
        "EN_ROUTE": {"ARRIVED", "CANCELLED"},
        "ARRIVED": {"RESOLVED", "CANCELLED"},
        "NO_AVAILABLE_PATROL": {"ASSIGNED", "CANCELLED"},
        "RESOLVED": set(),  # Terminal state
        "CANCELLED": set(), # Terminal state
    }

    def __init__(self):
        self.location_service = LocationService.get_instance()
        # Track declined officer IDs per SOS to prevent immediate redispatch loops
        self._declined_officers_map: Dict[int, Set[int]] = {}

    @classmethod
    def get_instance(cls) -> "DispatchService":
        if cls._instance is None:
            cls._instance = DispatchService()
        return cls._instance

    def _compute_approx_dist(self, sos: SOSRequest) -> Optional[float]:
        """Compute geodesic approximate distance between emergency and assigned patrol."""
        if sos.assigned_patrol and sos.assigned_patrol.current_latitude and sos.assigned_patrol.current_longitude:
            return round(
                self.location_service.haversine_distance(
                    sos.latitude,
                    sos.longitude,
                    sos.assigned_patrol.current_latitude,
                    sos.assigned_patrol.current_longitude,
                ),
                2,
            )
        return None


    # ==========================================
    # 1. NEAREST ELIGIBLE PATROL SELECTION
    # ==========================================

    async def find_nearest_eligible_patrol(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        exclude_officer_ids: Optional[Set[int]] = None,
        exclude_unit_ids: Optional[Set[int]] = None,
    ) -> Optional[Tuple[PatrolUnit, PoliceOfficer, float]]:
        """Find the nearest eligible, on-duty, available patrol unit and officer.
        
        Evaluates operational availability, verifies no conflicting active SOS dispatches,
        and sorts by geodesic Haversine distance.
        """
        exclude_officers = exclude_officer_ids or set()
        exclude_units = exclude_unit_ids or set()

        # 1. Find currently active/busy units and officers across unresolved SOS alerts
        active_sos_stmt = select(SOSRequest.assigned_patrol_id, SOSRequest.assigned_officer_id).where(
            SOSRequest.status.in_(["ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED"])
        )
        active_res = await db.execute(active_sos_stmt)
        active_pairs = active_res.all()

        busy_unit_ids: Set[int] = {p[0] for p in active_pairs if p[0] is not None}
        busy_officer_ids: Set[int] = {p[1] for p in active_pairs if p[1] is not None}

        # 2. Query eligible on-duty and available officers
        officer_stmt = (
            select(PoliceOfficer)
            .options(joinedload(PoliceOfficer.user))
            .where(
                and_(
                    PoliceOfficer.on_duty == True,
                    PoliceOfficer.is_available == True,
                    ~PoliceOfficer.id.in_(busy_officer_ids | exclude_officers),
                )
            )
        )
        off_res = await db.execute(officer_stmt)
        candidate_officers = off_res.scalars().unique().all()

        if not candidate_officers:
            logger.info("[DispatchService] No on-duty, available officers found for emergency dispatch.")
            return None

        # 3. Query eligible patrol units
        unit_stmt = (
            select(PatrolUnit)
            .where(
                and_(
                    PatrolUnit.status != "OFF_DUTY",
                    ~PatrolUnit.id.in_(busy_unit_ids | exclude_units),
                )
            )
        )
        unit_res = await db.execute(unit_stmt)
        candidate_units = unit_res.scalars().all()

        if not candidate_units:
            logger.info("[DispatchService] No available patrol units found for emergency dispatch.")
            return None

        # 4. Pair officers and units and score by proximity to emergency location
        scored_candidates: List[Tuple[PatrolUnit, PoliceOfficer, float]] = []

        for unit in candidate_units:
            u_lat = unit.current_latitude or 13.0827
            u_lon = unit.current_longitude or 80.2707

            dist_km = self.location_service.haversine_distance(latitude, longitude, u_lat, u_lon)

            # Pair with the first matching available officer
            for officer in candidate_officers:
                scored_candidates.append((unit, officer, dist_km))
                break

        if not scored_candidates:
            return None

        # Sort nearest -> farthest
        scored_candidates.sort(key=lambda x: x[2])
        return scored_candidates[0]

    # ==========================================
    # 2. DISPATCH CREATION & AUTO-ASSIGNMENT
    # ==========================================

    async def create_and_dispatch_sos(
        self,
        db: AsyncSession,
        citizen: User,
        latitude: float,
        longitude: float,
        notes: Optional[str] = None,
    ) -> SOSRequest:
        """Create citizen SOS request and transactionally dispatch the nearest available patrol."""
        # 1. Check for existing active distress call by this citizen
        active_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_patrol), joinedload(SOSRequest.assigned_officer))
            .where(
                and_(
                    SOSRequest.citizen_id == citizen.id,
                    SOSRequest.status.in_(["PENDING", "SUBMITTED", "ACTIVE", "ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED"]),
                )
            )
            .order_by(desc(SOSRequest.id))
        )
        existing_res = await db.execute(active_stmt)
        existing_sos = existing_res.scalar_one_or_none()
        if existing_sos:
            logger.info(f"[DispatchService] Citizen #{citizen.id} already has active SOS #{existing_sos.id}.")
            return existing_sos

        # 2. Create initial SOS entity in PENDING state
        sos = SOSRequest(
            citizen_id=citizen.id,
            latitude=latitude,
            longitude=longitude,
            status="PENDING",
            notes=notes,
            triggered_at=datetime.utcnow(),
        )
        db.add(sos)
        await db.flush()  # Obtain sos.id

        # 3. Locate nearest eligible patrol
        match = await self.find_nearest_eligible_patrol(db, latitude, longitude)

        if match:
            unit, officer, dist_km = match
            sos.assigned_patrol_id = unit.id
            sos.assigned_officer_id = officer.id
            sos.status = "ASSIGNED"

            # Reserve patrol resources
            unit.status = "DISPATCHED"
            officer.is_available = False
            logger.info(
                f"[DispatchService] SOS #{sos.id} successfully assigned to Unit '{unit.unit_code}' "
                f"(Officer: {officer.badge_number}) at distance ~{dist_km:.2f} km."
            )
        else:
            sos.status = "NO_AVAILABLE_PATROL"
            logger.warning(f"[DispatchService] No available patrol found for SOS #{sos.id}. Set to NO_AVAILABLE_PATROL.")

        await db.commit()

        # Eagerly reload with relationships to avoid async lazy loading issues
        reload_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_patrol), joinedload(SOSRequest.assigned_officer))
            .where(SOSRequest.id == sos.id)
        )
        res_reload = await db.execute(reload_stmt)
        loaded_sos = res_reload.scalar_one()

        # 4. Compute approximate distance for telemetry
        approx_dist = self._compute_approx_dist(loaded_sos)

        # 5. Live WebSocket Broadcast
        await live_sos_manager.broadcast_status_update(
            sos_id=loaded_sos.id,
            status=loaded_sos.status,
            approximate_distance_km=approx_dist,
            operational_details={
                "patrol_unit_id": loaded_sos.assigned_patrol_id,
                "officer_id": loaded_sos.assigned_officer_id,
                "latitude": loaded_sos.latitude,
                "longitude": loaded_sos.longitude,
            },
        )

        # 6. Notifications & Emergency Contact SMS (Non-blocking)
        try:
            await notification_service.send_emergency_contact_sms(db, citizen, loaded_sos)
        except Exception as sms_err:
            logger.error(f"[DispatchService] Emergency SMS notification encountered error non-blockingly: {sms_err}")

        try:
            await notification_service.notify_citizen_status_update(db, loaded_sos, loaded_sos.status, approximate_distance_km=approx_dist)
        except Exception as cit_err:
            logger.error(f"[DispatchService] Citizen status notification encountered error non-blockingly: {cit_err}")

        if loaded_sos.assigned_officer_id:
            try:
                await notification_service.notify_police_new_sos(db, loaded_sos, loaded_sos.assigned_officer_id)
            except Exception as pol_err:
                logger.error(f"[DispatchService] Police notification encountered error non-blockingly: {pol_err}")

        return loaded_sos

    # ==========================================
    # 3. POLICE ACCEPTANCE
    # ==========================================

    async def accept_dispatch(
        self,
        db: AsyncSession,
        sos_id: int,
        current_user: User,
    ) -> SOSRequest:
        """Assigned police officer accepts the emergency call (ASSIGNED -> ACCEPTED)."""
        stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res = await db.execute(stmt)
        sos = res.scalar_one_or_none()
        if not sos:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SOS alert #{sos_id} not found.")

        # Validate officer identity if police user
        if current_user.role == UserRole.POLICE:
            off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
            off_res = await db.execute(off_stmt)
            officer = off_res.scalar_one_or_none()
            if not officer:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Officer profile not found.")

            # Authorization check: only assigned officer can accept
            if sos.assigned_officer_id and sos.assigned_officer_id != officer.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You are not the assigned officer for this emergency dispatch.",
                )
            if not sos.assigned_officer_id:
                sos.assigned_officer_id = officer.id

        # State transition validation
        if sos.status not in ["ASSIGNED", "PENDING", "SUBMITTED", "ACTIVE"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot accept SOS #{sos_id} with current status '{sos.status}'. Required status: ASSIGNED.",
            )

        sos.status = "ACCEPTED"
        sos.updated_at = datetime.utcnow()

        await db.commit()

        reload_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res_reload = await db.execute(reload_stmt)
        loaded_sos = res_reload.scalar_one()

        approx_dist = self._compute_approx_dist(loaded_sos)
        await live_sos_manager.broadcast_status_update(
            sos_id=loaded_sos.id,
            status="ACCEPTED",
            approximate_distance_km=approx_dist,
            operational_details={"patrol_unit_id": loaded_sos.assigned_patrol_id, "officer_id": loaded_sos.assigned_officer_id},
        )
        await notification_service.notify_citizen_status_update(db, loaded_sos, "ACCEPTED", approximate_distance_km=approx_dist)

        return loaded_sos


    # ==========================================
    # 4. LIFECYCLE STATUS TRANSITIONS
    # ==========================================

    async def update_dispatch_status(
        self,
        db: AsyncSession,
        sos_id: int,
        target_status: str,
        current_user: User,
        notes: Optional[str] = None,
    ) -> SOSRequest:
        """Progress SOS status through validated state transitions (ACCEPTED -> EN_ROUTE -> ARRIVED -> RESOLVED)."""
        target_status = target_status.upper().strip()

        stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res = await db.execute(stmt)
        sos = res.scalar_one_or_none()
        if not sos:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SOS alert #{sos_id} not found.")

        # Authorization check: police must be the assigned officer
        if current_user.role == UserRole.POLICE:
            off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
            off_res = await db.execute(off_stmt)
            officer = off_res.scalar_one_or_none()
            if not officer:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Officer profile not found.")

            if sos.assigned_officer_id and sos.assigned_officer_id != officer.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You are not authorized to update this emergency dispatch.",
                )

        # Strict State Machine Transition Validation
        allowed_next = self.ALLOWED_TRANSITIONS.get(sos.status, set())
        if target_status not in allowed_next and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid transition from '{sos.status}' to '{target_status}'. Allowed: {sorted(list(allowed_next))}",
            )

        sos.status = target_status
        if notes:
            sos.notes = notes

        # Handle Resource Release upon Resolution or Cancellation
        if target_status in ["RESOLVED", "CANCELLED"]:
            if target_status == "RESOLVED":
                sos.resolved_at = datetime.utcnow()

            # 1. Determine whether the assigned officer has an existing active PatrolAssignment
            active_prp_assignment: Optional[PatrolAssignment] = None
            if sos.assigned_officer_id:
                assign_stmt = (
                    select(PatrolAssignment)
                    .where(
                        and_(
                            PatrolAssignment.officer_id == sos.assigned_officer_id,
                            PatrolAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "AT_PRP"]),
                        )
                    )
                    .order_by(desc(PatrolAssignment.id))
                )
                assign_res = await db.execute(assign_stmt)
                active_prp_assignment = assign_res.scalars().first()

            # 2. If active assignment is currently AT_PRP, restore SAME assignment to ACKNOWLEDGED
            if active_prp_assignment and active_prp_assignment.status == "AT_PRP":
                active_prp_assignment.status = "ACKNOWLEDGED"
                active_prp_assignment.updated_at = datetime.utcnow()
                logger.info(
                    f"[DispatchService] SOS #{sos.id} {target_status}. Restored active Assignment "
                    f"#{active_prp_assignment.id} to ACKNOWLEDGED for Officer #{sos.assigned_officer_id}."
                )

            # 3. Synchronize patrol unit status
            if sos.assigned_patrol:
                if active_prp_assignment and active_prp_assignment.status in ["ASSIGNED", "ACKNOWLEDGED"]:
                    # Unit is in transit / deployed under an active PRP assignment
                    sos.assigned_patrol.status = "DISPATCHED"
                else:
                    sos.assigned_patrol.status = "AVAILABLE"

            # 4. Release officer availability (on_duty remains unchanged)
            if sos.assigned_officer and sos.assigned_officer.on_duty:
                sos.assigned_officer.is_available = True

            logger.info(f"[DispatchService] SOS #{sos.id} {target_status}. Released patrol unit and officer availability.")

        sos.updated_at = datetime.utcnow()
        await db.commit()

        reload_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res_reload = await db.execute(reload_stmt)
        loaded_sos = res_reload.scalar_one()

        approx_dist = self._compute_approx_dist(loaded_sos)
        await live_sos_manager.broadcast_status_update(
            sos_id=loaded_sos.id,
            status=target_status,
            approximate_distance_km=approx_dist,
            operational_details={
                "patrol_unit_id": loaded_sos.assigned_patrol_id,
                "officer_id": loaded_sos.assigned_officer_id,
                "notes": loaded_sos.notes,
            },
        )
        await notification_service.notify_citizen_status_update(db, loaded_sos, target_status, approximate_distance_km=approx_dist)

        return loaded_sos

    # ==========================================
    # 5. POLICE DECLINE & REDISPATCH
    # ==========================================

    async def decline_and_redispatch(
        self,
        db: AsyncSession,
        sos_id: int,
        current_user: User,
    ) -> SOSRequest:
        """Officer declines dispatch; releases assignment and searches for next nearest patrol without loops."""
        stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res = await db.execute(stmt)
        sos = res.scalar_one_or_none()
        if not sos:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SOS alert #{sos_id} not found.")

        # Authorization & Officer verification
        off_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == current_user.id)
        off_res = await db.execute(off_stmt)
        officer = off_res.scalar_one_or_none()
        if not officer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Officer profile not found.")

        if sos.assigned_officer_id and sos.assigned_officer_id != officer.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the assigned officer can decline this dispatch.",
            )

        if sos.status in ["RESOLVED", "CANCELLED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot decline terminal SOS #{sos_id} with status '{sos.status}'.",
            )

        # 1. Release current officer and patrol reservation
        if sos.assigned_patrol:
            sos.assigned_patrol.status = "AVAILABLE"
        if sos.assigned_officer and sos.assigned_officer.on_duty:
            sos.assigned_officer.is_available = True

        # Track declined officer to prevent immediate re-assignment loop
        if sos_id not in self._declined_officers_map:
            self._declined_officers_map[sos_id] = set()
        self._declined_officers_map[sos_id].add(officer.id)

        # 2. Redispatch to next nearest eligible patrol
        match = await self.find_nearest_eligible_patrol(
            db=db,
            latitude=sos.latitude,
            longitude=sos.longitude,
            exclude_officer_ids=self._declined_officers_map[sos_id],
        )

        if match:
            next_unit, next_officer, dist_km = match
            sos.assigned_patrol_id = next_unit.id
            sos.assigned_officer_id = next_officer.id
            sos.status = "ASSIGNED"

            next_unit.status = "DISPATCHED"
            next_officer.is_available = False
            logger.info(
                f"[DispatchService] SOS #{sos.id} redispatched to Unit '{next_unit.unit_code}' "
                f"(Officer: {next_officer.badge_number}) at distance ~{dist_km:.2f} km."
            )
        else:
            sos.assigned_patrol_id = None
            sos.assigned_officer_id = None
            sos.status = "NO_AVAILABLE_PATROL"
            logger.warning(f"[DispatchService] No other patrol available for redispatch of SOS #{sos.id}.")

        sos.updated_at = datetime.utcnow()
        await db.commit()

        reload_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res_reload = await db.execute(reload_stmt)
        loaded_sos = res_reload.scalar_one()

        approx_dist = self._compute_approx_dist(loaded_sos)
        await live_sos_manager.broadcast_status_update(
            sos_id=loaded_sos.id,
            status=loaded_sos.status,
            approximate_distance_km=approx_dist,
            operational_details={
                "patrol_unit_id": loaded_sos.assigned_patrol_id,
                "officer_id": loaded_sos.assigned_officer_id,
                "declined": True,
            },
        )
        await notification_service.notify_citizen_status_update(db, loaded_sos, loaded_sos.status, approximate_distance_km=approx_dist)
        if loaded_sos.assigned_officer_id:
            await notification_service.notify_police_new_sos(db, loaded_sos, loaded_sos.assigned_officer_id)

        return loaded_sos

    # ==========================================
    # 6. ADMIN MANUAL DISPATCH OVERRIDE
    # ==========================================

    async def manual_admin_dispatch(
        self,
        db: AsyncSession,
        sos_id: int,
        patrol_unit_id: int,
        officer_id: Optional[int] = None,
    ) -> SOSRequest:
        """Admin manually assigns or overrides patrol unit dispatch for an emergency."""
        stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res = await db.execute(stmt)
        sos = res.scalar_one_or_none()
        if not sos:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SOS alert #{sos_id} not found.")

        # Check unit validity
        u_stmt = select(PatrolUnit).where(PatrolUnit.id == patrol_unit_id)
        u_res = await db.execute(u_stmt)
        unit = u_res.scalar_one_or_none()
        if not unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patrol unit #{patrol_unit_id} not found.")

        # Concurrency verification: check if patrol unit is already responding to another active SOS
        busy_stmt = select(SOSRequest).where(
            and_(
                SOSRequest.assigned_patrol_id == patrol_unit_id,
                SOSRequest.id != sos_id,
                SOSRequest.status.in_(["ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED"]),
            )
        )
        busy_res = await db.execute(busy_stmt)
        busy_sos = busy_res.scalar_one_or_none()
        if busy_sos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patrol unit '{unit.unit_code}' is currently responding to active SOS #{busy_sos.id}.",
            )

        # Release previously assigned resources if any
        if sos.assigned_patrol and sos.assigned_patrol.id != patrol_unit_id:
            sos.assigned_patrol.status = "AVAILABLE"
        if sos.assigned_officer and (officer_id is None or sos.assigned_officer.id != officer_id):
            if sos.assigned_officer.on_duty:
                sos.assigned_officer.is_available = True

        sos.assigned_patrol_id = unit.id
        unit.status = "DISPATCHED"

        if officer_id:
            off_stmt = select(PoliceOfficer).where(PoliceOfficer.id == officer_id)
            off_res = await db.execute(off_stmt)
            officer = off_res.scalar_one_or_none()
            if officer:
                sos.assigned_officer_id = officer.id
                officer.is_available = False

        sos.status = "ASSIGNED"
        sos.updated_at = datetime.utcnow()

        await db.commit()

        reload_stmt = (
            select(SOSRequest)
            .options(joinedload(SOSRequest.assigned_officer), joinedload(SOSRequest.assigned_patrol))
            .where(SOSRequest.id == sos_id)
        )
        res_reload = await db.execute(reload_stmt)
        loaded_sos = res_reload.scalar_one()

        approx_dist = self._compute_approx_dist(loaded_sos)
        await live_sos_manager.broadcast_status_update(
            sos_id=loaded_sos.id,
            status="ASSIGNED",
            approximate_distance_km=approx_dist,
            operational_details={
                "patrol_unit_id": loaded_sos.assigned_patrol_id,
                "officer_id": loaded_sos.assigned_officer_id,
                "admin_override": True,
            },
        )
        await notification_service.notify_citizen_status_update(db, loaded_sos, "ASSIGNED", approximate_distance_km=approx_dist)
        if loaded_sos.assigned_officer_id:
            await notification_service.notify_police_new_sos(db, loaded_sos, loaded_sos.assigned_officer_id)

        return loaded_sos


dispatch_service = DispatchService.get_instance()

