"""SafeZone Police, Patrol Resource and PRP Assignment Service.

Manages:
- Police officer profiles and administrative onboarding
- Patrol unit vehicle resources and availability
- Automatic and manual patrol assignment to approved PRPs
- Preventing incompatible duplicate assignments
- Assignment status transitions (ASSIGNED -> ACKNOWLEDGED -> AT_PRP -> COMPLETED)
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.police import PoliceOfficer, PatrolUnit, LocationUpdate
from app.models.optimization import PRPLocation, PatrolAssignment, OptimizationRun
from app.models.sos import SOSRequest
from app.services.location_service import LocationService
from app.services.live_manager import live_sos_manager
from app.core.security import get_password_hash

from app.optimization.assignment import (
    patrol_assignment_engine,
    AssignmentCandidateUnit,
    AssignmentCandidateOfficer,
    AssignmentTargetPRP,
    AssignmentSolverResult,
)
from app.schemas.patrol import (
    PoliceOfficerCreateRequest,
    PoliceOfficerUpdateRequest,
    PoliceOfficerResponse,
    PatrolUnitCreateRequest,
    PatrolUnitUpdateRequest,
    PatrolUnitResponse,
    ManualAssignmentRequest,
    AutoAssignmentRequest,
    PatrolAssignmentResponse,
    AutoAssignmentResponse,
)
from app.core.logging import logger


class PatrolService:
    _instance: Optional["PatrolService"] = None

    @classmethod
    def get_instance(cls) -> "PatrolService":
        if cls._instance is None:
            cls._instance = PatrolService()
        return cls._instance

    # ==========================================
    # 1. POLICE OFFICER MANAGEMENT
    # ==========================================

    async def create_police_officer(
        self,
        db: AsyncSession,
        req: PoliceOfficerCreateRequest,
    ) -> PoliceOfficerResponse:
        """Create new Police Officer account (Admin Only)."""
        # Check email uniqueness
        email_stmt = select(User).where(User.email == req.email.lower())
        res = await db.execute(email_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{req.email}' already exists.",
            )

        # Check badge uniqueness
        badge_stmt = select(PoliceOfficer).where(PoliceOfficer.badge_number == req.badge_number.upper())
        res_badge = await db.execute(badge_stmt)
        if res_badge.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Officer with badge number '{req.badge_number}' already exists.",
            )

        # Create User
        user = User(
            email=req.email.lower(),
            hashed_password=get_password_hash(req.password),
            full_name=req.full_name,
            phone_number=req.phone_number,
            role=UserRole.POLICE,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        # Create PoliceOfficer Profile
        officer = PoliceOfficer(
            user_id=user.id,
            badge_number=req.badge_number.upper(),
            rank=req.rank,
            station_name=req.station_name,
            on_duty=req.on_duty,
            is_available=True,
        )
        db.add(officer)
        await db.commit()
        await db.refresh(officer)

        return PoliceOfficerResponse(
            id=officer.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
            badge_number=officer.badge_number,
            rank=officer.rank,
            station_name=officer.station_name,
            on_duty=officer.on_duty,
            is_available=officer.is_available,
            is_active=user.is_active,
            created_at=officer.created_at,
        )

    async def update_police_officer(
        self,
        db: AsyncSession,
        officer_id: int,
        req: PoliceOfficerUpdateRequest,
    ) -> PoliceOfficerResponse:
        """Update Police Officer details and availability."""
        stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).where(PoliceOfficer.id == officer_id)
        result = await db.execute(stmt)
        officer = result.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Police officer #{officer_id} not found.",
            )

        if req.rank is not None:
            officer.rank = req.rank
        if req.station_name is not None:
            officer.station_name = req.station_name
        if req.on_duty is not None:
            officer.on_duty = req.on_duty
        if req.is_available is not None:
            officer.is_available = req.is_available

        if officer.user:
            if req.full_name is not None:
                officer.user.full_name = req.full_name
            if req.phone_number is not None:
                officer.user.phone_number = req.phone_number
            if req.is_active is not None:
                officer.user.is_active = req.is_active

        await db.commit()
        await db.refresh(officer)

        return PoliceOfficerResponse(
            id=officer.id,
            user_id=officer.user_id,
            email=officer.user.email if officer.user else "",
            full_name=officer.user.full_name if officer.user else "",
            phone_number=officer.user.phone_number if officer.user else None,
            badge_number=officer.badge_number,
            rank=officer.rank,
            station_name=officer.station_name,
            on_duty=officer.on_duty,
            is_available=officer.is_available,
            is_active=officer.user.is_active if officer.user else False,
            created_at=officer.created_at,
        )

    async def list_police_officers(
        self,
        db: AsyncSession,
        station_name: Optional[str] = None,
        on_duty: Optional[bool] = None,
        is_available: Optional[bool] = None,
    ) -> List[PoliceOfficerResponse]:
        """List police officers with optional filters."""
        stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).order_by(PoliceOfficer.id)

        if station_name:
            stmt = stmt.where(PoliceOfficer.station_name.ilike(f"%{station_name}%"))
        if on_duty is not None:
            stmt = stmt.where(PoliceOfficer.on_duty == on_duty)
        if is_available is not None:
            stmt = stmt.where(PoliceOfficer.is_available == is_available)

        result = await db.execute(stmt)
        officers = result.scalars().all()

        return [
            PoliceOfficerResponse(
                id=o.id,
                user_id=o.user_id,
                email=o.user.email if o.user else "",
                full_name=o.user.full_name if o.user else "",
                phone_number=o.user.phone_number if o.user else None,
                badge_number=o.badge_number,
                rank=o.rank,
                station_name=o.station_name,
                on_duty=o.on_duty,
                is_available=o.is_available,
                is_active=o.user.is_active if o.user else False,
                created_at=o.created_at,
            )
            for o in officers
        ]

    # ==========================================
    # 2. PATROL UNIT RESOURCE MANAGEMENT
    # ==========================================

    async def create_patrol_unit(
        self,
        db: AsyncSession,
        req: PatrolUnitCreateRequest,
    ) -> PatrolUnitResponse:
        """Create new Patrol Unit / Vehicle resource."""
        code_stmt = select(PatrolUnit).where(PatrolUnit.unit_code == req.unit_code.upper())
        res = await db.execute(code_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patrol unit '{req.unit_code}' already exists.",
            )

        unit = PatrolUnit(
            unit_code=req.unit_code.upper(),
            unit_type=req.unit_type.upper(),
            status=req.status.upper(),
            current_latitude=req.current_latitude,
            current_longitude=req.current_longitude,
            last_location_update=datetime.utcnow() if req.current_latitude else None,
        )
        db.add(unit)
        await db.commit()
        await db.refresh(unit)

        return PatrolUnitResponse(
            id=unit.id,
            unit_code=unit.unit_code,
            unit_type=unit.unit_type,
            status=unit.status,
            current_latitude=unit.current_latitude,
            current_longitude=unit.current_longitude,
            last_location_update=unit.last_location_update,
            created_at=unit.created_at,
        )

    async def update_patrol_unit(
        self,
        db: AsyncSession,
        unit_id: int,
        req: PatrolUnitUpdateRequest,
    ) -> PatrolUnitResponse:
        """Update patrol unit status and location."""
        stmt = select(PatrolUnit).where(PatrolUnit.id == unit_id)
        result = await db.execute(stmt)
        unit = result.scalar_one_or_none()
        if not unit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patrol unit #{unit_id} not found.",
            )

        if req.unit_type is not None:
            unit.unit_type = req.unit_type.upper()
        if req.status is not None:
            unit.status = req.status.upper()
        if req.current_latitude is not None and req.current_longitude is not None:
            unit.current_latitude = req.current_latitude
            unit.current_longitude = req.current_longitude
            unit.last_location_update = datetime.utcnow()

        await db.commit()
        await db.refresh(unit)

        return PatrolUnitResponse(
            id=unit.id,
            unit_code=unit.unit_code,
            unit_type=unit.unit_type,
            status=unit.status,
            current_latitude=unit.current_latitude,
            current_longitude=unit.current_longitude,
            last_location_update=unit.last_location_update,
            created_at=unit.created_at,
        )

    async def list_patrol_units(
        self,
        db: AsyncSession,
        status_filter: Optional[str] = None,
        unit_type: Optional[str] = None,
    ) -> List[PatrolUnitResponse]:
        """List patrol units with optional filters."""
        stmt = select(PatrolUnit).order_by(PatrolUnit.id)
        if status_filter:
            stmt = stmt.where(PatrolUnit.status == status_filter.upper())
        if unit_type:
            stmt = stmt.where(PatrolUnit.unit_type == unit_type.upper())

        result = await db.execute(stmt)
        units = result.scalars().all()

        return [
            PatrolUnitResponse(
                id=u.id,
                unit_code=u.unit_code,
                unit_type=u.unit_type,
                status=u.status,
                current_latitude=u.current_latitude,
                current_longitude=u.current_longitude,
                last_location_update=u.last_location_update,
                created_at=u.created_at,
            )
            for u in units
        ]

    # ==========================================
    # 3. PATROL ASSIGNMENT & LIFECYCLE
    # ==========================================

    async def create_manual_assignment(
        self,
        db: AsyncSession,
        req: ManualAssignmentRequest,
    ) -> PatrolAssignmentResponse:
        """Manually assign an officer and patrol unit to a PRP with duplicate validation."""
        # 1. Validate PRP
        prp_stmt = select(PRPLocation).where(PRPLocation.id == req.prp_id)
        res_prp = await db.execute(prp_stmt)
        prp = res_prp.scalar_one_or_none()
        if not prp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PRP #{req.prp_id} not found.",
            )

        # 2. Validate Patrol Unit
        unit_stmt = select(PatrolUnit).where(PatrolUnit.id == req.patrol_unit_id)
        res_u = await db.execute(unit_stmt)
        unit = res_u.scalar_one_or_none()
        if not unit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patrol unit #{req.patrol_unit_id} not found.",
            )

        # 3. Validate Officer
        officer_stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).where(PoliceOfficer.id == req.officer_id)
        res_o = await db.execute(officer_stmt)
        officer = res_o.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Police officer #{req.officer_id} not found.",
            )

        # 4. Incompatible Duplicate Assignment Check
        now = datetime.utcnow()
        shift_start = req.shift_start or now
        if shift_start.tzinfo is not None:
            shift_start = shift_start.astimezone(timezone.utc).replace(tzinfo=None)

        shift_end = req.shift_end or (shift_start + timedelta(hours=8))
        if shift_end.tzinfo is not None:
            shift_end = shift_end.astimezone(timezone.utc).replace(tzinfo=None)

        active_statuses = ["ASSIGNED", "ACKNOWLEDGED", "AT_PRP"]
        dup_stmt = select(PatrolAssignment).where(
            and_(
                PatrolAssignment.status.in_(active_statuses),
                or_(
                    PatrolAssignment.patrol_unit_id == req.patrol_unit_id,
                    PatrolAssignment.officer_id == req.officer_id,
                    PatrolAssignment.prp_id == req.prp_id,
                ),
            )
        )
        res_dup = await db.execute(dup_stmt)
        existing_dup = res_dup.scalar_one_or_none()
        if existing_dup:
            conflict_target = "Patrol unit" if existing_dup.patrol_unit_id == req.patrol_unit_id else ("Officer" if existing_dup.officer_id == req.officer_id else "PRP")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incompatible duplicate assignment: {conflict_target} is already actively assigned (Assignment #{existing_dup.id}).",
            )

        # 5. Create Assignment Record
        assignment = PatrolAssignment(
            prp_id=req.prp_id,
            patrol_unit_id=req.patrol_unit_id,
            officer_id=req.officer_id,
            shift_start=shift_start,
            shift_end=shift_end,
            status="ASSIGNED",
        )
        db.add(assignment)

        # Update resource statuses
        unit.status = "DISPATCHED"
        # Note: PRP patrol assignment does not make an on-duty officer unavailable for emergency SOS dispatch
        prp.status = "ACTIVE"

        await db.commit()
        await db.refresh(assignment)

        return self._format_assignment_response(assignment, prp, unit, officer)

    async def run_auto_assignment(
        self,
        db: AsyncSession,
        req: AutoAssignmentRequest,
    ) -> AutoAssignmentResponse:
        """Run automated optimization assignment of available resources to unassigned PRPs."""
        now = datetime.utcnow()
        shift_start = req.shift_start or now
        if shift_start.tzinfo is not None:
            shift_start = shift_start.astimezone(timezone.utc).replace(tzinfo=None)

        shift_end = req.shift_end or (shift_start + timedelta(hours=8))
        if shift_end.tzinfo is not None:
            shift_end = shift_end.astimezone(timezone.utc).replace(tzinfo=None)

        # 1. Fetch unassigned PRPs (Active/Approved/Recommended)
        active_statuses = ["ASSIGNED", "ACKNOWLEDGED", "AT_PRP"]
        assigned_prp_subq = select(PatrolAssignment.prp_id).where(PatrolAssignment.status.in_(active_statuses))

        prp_stmt = select(PRPLocation).where(
            and_(
                PRPLocation.status.in_(["RECOMMENDED", "APPROVED", "ACTIVE"]),
                PRPLocation.id.not_in(assigned_prp_subq),
            )
        )
        if req.optimization_run_id:
            prp_stmt = prp_stmt.where(PRPLocation.optimization_run_id == req.optimization_run_id)

        res_prps = await db.execute(prp_stmt)
        target_prp_records = res_prps.scalars().all()

        target_prps = [
            AssignmentTargetPRP(
                prp_id=p.id,
                rank=p.rank,
                latitude=p.latitude,
                longitude=p.longitude,
                ward_no=p.ward_no,
                zone_no=p.zone_no,
                zone_name=p.zone_name,
                risk_score=p.risk_score,
                coverage_radius_km=p.coverage_radius_km,
            )
            for p in target_prp_records
        ]

        # 2. Fetch busy units and officers to prevent duplicate assignment
        busy_units_stmt = select(PatrolAssignment.patrol_unit_id).where(
            and_(PatrolAssignment.status.in_(active_statuses), PatrolAssignment.patrol_unit_id.is_not(None))
        )
        busy_officers_stmt = select(PatrolAssignment.officer_id).where(
            and_(PatrolAssignment.status.in_(active_statuses), PatrolAssignment.officer_id.is_not(None))
        )
        res_bu = await db.execute(busy_units_stmt)
        res_bo = await db.execute(busy_officers_stmt)
        busy_unit_ids: Set[int] = set(res_bu.scalars().all())
        busy_officer_ids: Set[int] = set(res_bo.scalars().all())

        # 3. Fetch available units
        unit_stmt = select(PatrolUnit).where(
            and_(
                PatrolUnit.status == "AVAILABLE",
                PatrolUnit.id.not_in(busy_unit_ids) if busy_unit_ids else True,
            )
        )
        res_u = await db.execute(unit_stmt)
        unit_records = res_u.scalars().all()
        candidate_units = [
            AssignmentCandidateUnit(
                unit_id=u.id,
                unit_code=u.unit_code,
                unit_type=u.unit_type,
                current_latitude=u.current_latitude,
                current_longitude=u.current_longitude,
                is_available=True,
            )
            for u in unit_records
        ]

        # 4. Fetch available on-duty officers
        officer_stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).where(
            and_(
                PoliceOfficer.on_duty == True,
                PoliceOfficer.is_available == True,
                PoliceOfficer.id.not_in(busy_officer_ids) if busy_officer_ids else True,
            )
        )
        res_o = await db.execute(officer_stmt)
        officer_records = res_o.scalars().all()
        candidate_officers = [
            AssignmentCandidateOfficer(
                officer_id=o.id,
                badge_number=o.badge_number,
                rank=o.rank,
                station_name=o.station_name,
                on_duty=o.on_duty,
                is_available=True,
            )
            for o in officer_records
        ]

        # 5. Solve Optimal Assignment
        solver_res: AssignmentSolverResult = patrol_assignment_engine.solve_assignment(
            target_prps=target_prps,
            available_units=candidate_units,
            available_officers=candidate_officers,
            busy_unit_ids=busy_unit_ids,
            busy_officer_ids=busy_officer_ids,
        )

        unit_map = {u.id: u for u in unit_records}
        officer_map = {o.id: o for o in officer_records}
        prp_map = {p.id: p for p in target_prp_records}

        created_assignments: List[PatrolAssignmentResponse] = []

        # 6. Persist matches
        for m in solver_res.matches:
            assignment = PatrolAssignment(
                prp_id=m.prp_id,
                patrol_unit_id=m.patrol_unit_id,
                officer_id=m.officer_id,
                shift_start=shift_start,
                shift_end=shift_end,
                status="ASSIGNED",
            )
            db.add(assignment)

            u_obj = unit_map.get(m.patrol_unit_id)
            if u_obj:
                u_obj.status = "DISPATCHED"

            o_obj = officer_map.get(m.officer_id)
            # Note: PRP patrol assignment does not make an on-duty officer unavailable for emergency SOS dispatch

            p_obj = prp_map.get(m.prp_id)
            if p_obj:
                p_obj.status = "ACTIVE"

            await db.flush()
            created_assignments.append(
                self._format_assignment_response(assignment, p_obj, u_obj, o_obj)
            )

        await db.commit()

        return AutoAssignmentResponse(
            status=solver_res.status,
            total_target_prps=solver_res.total_target_prps,
            assigned_count=solver_res.assigned_count,
            unassigned_prps_count=len(solver_res.unassigned_prp_ids),
            assignments=created_assignments,
        )

    async def update_assignment_status(
        self,
        db: AsyncSession,
        assignment_id: int,
        new_status: str,
        current_user: User,
    ) -> PatrolAssignmentResponse:
        """Transition patrol assignment lifecycle status."""
        valid_transitions = ["ASSIGNED", "ACKNOWLEDGED", "AT_PRP", "UNAVAILABLE", "COMPLETED", "CANCELLED"]
        target_status = new_status.upper()
        if target_status not in valid_transitions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid assignment status '{new_status}'. Allowed: {valid_transitions}",
            )

        stmt = (
            select(PatrolAssignment)
            .options(
                joinedload(PatrolAssignment.prp),
                joinedload(PatrolAssignment.patrol_unit),
                joinedload(PatrolAssignment.officer).joinedload(PoliceOfficer.user),
            )
            .where(PatrolAssignment.id == assignment_id)
        )
        res = await db.execute(stmt)
        assignment = res.scalar_one_or_none()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patrol assignment #{assignment_id} not found.",
            )

        # Authorization: Police officer can only update their own assignment; Admin can update any
        if current_user.role == UserRole.POLICE:
            if not assignment.officer or assignment.officer.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: You may only manage your own assigned patrol.",
                )

        assignment.status = target_status

        # Synchronize associated unit and officer statuses
        if target_status == "AT_PRP" and assignment.patrol_unit:
            assignment.patrol_unit.status = "ON_PATROL"
        elif target_status in ["COMPLETED", "CANCELLED"]:
            if assignment.patrol_unit:
                assignment.patrol_unit.status = "AVAILABLE"
            if assignment.officer and assignment.officer.on_duty:
                assignment.officer.is_available = True
        elif target_status == "UNAVAILABLE":
            if assignment.patrol_unit:
                assignment.patrol_unit.status = "AVAILABLE"
            if assignment.officer:
                assignment.officer.is_available = False

        await db.commit()
        await db.refresh(assignment)

        return self._format_assignment_response(
            assignment, assignment.prp, assignment.patrol_unit, assignment.officer
        )

    async def get_my_active_assignment(
        self,
        db: AsyncSession,
        officer_user_id: int,
    ) -> Optional[PatrolAssignmentResponse]:
        """Fetch active assignment for logged-in police officer."""
        officer_stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == officer_user_id)
        res_o = await db.execute(officer_stmt)
        officer = res_o.scalar_one_or_none()
        if not officer:
            return None

        active_statuses = ["ASSIGNED", "ACKNOWLEDGED", "AT_PRP"]
        stmt = (
            select(PatrolAssignment)
            .options(
                joinedload(PatrolAssignment.prp),
                joinedload(PatrolAssignment.patrol_unit),
                joinedload(PatrolAssignment.officer).joinedload(PoliceOfficer.user),
            )
            .where(
                and_(
                    PatrolAssignment.officer_id == officer.id,
                    PatrolAssignment.status.in_(active_statuses),
                )
            )
            .order_by(desc(PatrolAssignment.id))
        )
        res_a = await db.execute(stmt)
        assignment = res_a.scalar_one_or_none()
        if not assignment:
            return None

        return self._format_assignment_response(
            assignment, assignment.prp, assignment.patrol_unit, assignment.officer
        )

    async def list_assignments(
        self,
        db: AsyncSession,
        status_filter: Optional[str] = None,
        officer_id: Optional[int] = None,
        patrol_unit_id: Optional[int] = None,
        prp_id: Optional[int] = None,
    ) -> List[PatrolAssignmentResponse]:
        """List assignments with multi-field filtering."""
        stmt = (
            select(PatrolAssignment)
            .options(
                joinedload(PatrolAssignment.prp),
                joinedload(PatrolAssignment.patrol_unit),
                joinedload(PatrolAssignment.officer).joinedload(PoliceOfficer.user),
            )
            .order_by(desc(PatrolAssignment.id))
        )
        if status_filter:
            stmt = stmt.where(PatrolAssignment.status == status_filter.upper())
        if officer_id:
            stmt = stmt.where(PatrolAssignment.officer_id == officer_id)
        if patrol_unit_id:
            stmt = stmt.where(PatrolAssignment.patrol_unit_id == patrol_unit_id)
        if prp_id:
            stmt = stmt.where(PatrolAssignment.prp_id == prp_id)

        res = await db.execute(stmt)
        assignments = res.scalars().all()

        return [
            self._format_assignment_response(a, a.prp, a.patrol_unit, a.officer)
            for a in assignments
        ]

    @staticmethod
    def _format_assignment_response(
        assignment: PatrolAssignment,
        prp: Optional[PRPLocation],
        unit: Optional[PatrolUnit],
        officer: Optional[PoliceOfficer],
    ) -> PatrolAssignmentResponse:
        """Format database entities into structured assignment response."""
        prp_data = None
        if prp:
            prp_data = {
                "id": prp.id,
                "rank": prp.rank,
                "latitude": prp.latitude,
                "longitude": prp.longitude,
                "ward_no": prp.ward_no,
                "zone_no": prp.zone_no,
                "zone_name": prp.zone_name,
                "risk_score": prp.risk_score,
                "coverage_radius_km": prp.coverage_radius_km,
                "status": prp.status,
            }

        unit_data = None
        if unit:
            unit_data = {
                "id": unit.id,
                "unit_code": unit.unit_code,
                "unit_type": unit.unit_type,
                "status": unit.status,
                "current_latitude": unit.current_latitude,
                "current_longitude": unit.current_longitude,
            }

        officer_data = None
        if officer:
            officer_data = {
                "id": officer.id,
                "badge_number": officer.badge_number,
                "rank": officer.rank,
                "station_name": officer.station_name,
                "full_name": officer.user.full_name if officer.user else "",
                "phone_number": officer.user.phone_number if officer.user else None,
            }

        return PatrolAssignmentResponse(
            id=assignment.id,
            prp_id=assignment.prp_id,
            patrol_unit_id=assignment.patrol_unit_id,
            officer_id=assignment.officer_id,
            shift_start=assignment.shift_start,
            shift_end=assignment.shift_end,
            status=assignment.status,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            prp_details=prp_data,
            patrol_unit_details=unit_data,
            officer_details=officer_data,
        )

    async def get_officer_by_user_id(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> PoliceOfficerResponse:
        """Fetch Police Officer profile by authenticated user ID."""
        stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).where(PoliceOfficer.user_id == user_id)
        res = await db.execute(stmt)
        officer = res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Police officer profile not found for the current user.",
            )
        return PoliceOfficerResponse(
            id=officer.id,
            user_id=officer.user_id,
            email=officer.user.email if officer.user else "",
            full_name=officer.user.full_name if officer.user else "",
            phone_number=officer.user.phone_number if officer.user else None,
            badge_number=officer.badge_number,
            rank=officer.rank,
            station_name=officer.station_name,
            on_duty=officer.on_duty,
            is_available=officer.is_available,
            is_active=officer.user.is_active if officer.user else False,
            created_at=officer.created_at,
        )

    async def update_duty_status(
        self,
        db: AsyncSession,
        user_id: int,
        on_duty: bool,
        is_available: Optional[bool] = None,
    ) -> PoliceOfficerResponse:
        """Update police officer duty and availability status."""
        stmt = select(PoliceOfficer).options(joinedload(PoliceOfficer.user)).where(PoliceOfficer.user_id == user_id)
        res = await db.execute(stmt)
        officer = res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Police officer profile not found for the current user.",
            )
        officer.on_duty = on_duty
        if is_available is not None:
            officer.is_available = is_available
        elif not on_duty:
            officer.is_available = False
        else:
            officer.is_available = True

        await db.commit()
        await db.refresh(officer)

        return PoliceOfficerResponse(
            id=officer.id,
            user_id=officer.user_id,
            email=officer.user.email if officer.user else "",
            full_name=officer.user.full_name if officer.user else "",
            phone_number=officer.user.phone_number if officer.user else None,
            badge_number=officer.badge_number,
            rank=officer.rank,
            station_name=officer.station_name,
            on_duty=officer.on_duty,
            is_available=officer.is_available,
            is_active=officer.user.is_active if officer.user else False,
            created_at=officer.created_at,
        )

    async def record_officer_location(
        self,
        db: AsyncSession,
        user_id: int,
        latitude: float,
        longitude: float,
    ) -> Dict[str, Any]:
        """Record officer location telemetry and update active unit location if assigned."""
        stmt = select(PoliceOfficer).where(PoliceOfficer.user_id == user_id)
        res = await db.execute(stmt)
        officer = res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Police officer profile not found for the current user.",
            )

        # Log location update
        loc_log = LocationUpdate(
            officer_id=officer.id,
            latitude=latitude,
            longitude=longitude,
            recorded_at=datetime.utcnow(),
        )
        db.add(loc_log)

        # If officer has an active assignment with a patrol unit, update unit coordinates as well
        assign_stmt = (
            select(PatrolAssignment)
            .where(
                and_(
                    PatrolAssignment.officer_id == officer.id,
                    PatrolAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "AT_PRP"]),
                )
            )
            .order_by(desc(PatrolAssignment.id))
        )
        assign_res = await db.execute(assign_stmt)
        active_assign = assign_res.scalar_one_or_none()

        if active_assign and active_assign.patrol_unit_id:
            unit_stmt = select(PatrolUnit).where(PatrolUnit.id == active_assign.patrol_unit_id)
            u_res = await db.execute(unit_stmt)
            unit = u_res.scalar_one_or_none()
            if unit:
                unit.current_latitude = latitude
                unit.current_longitude = longitude
                unit.last_location_update = datetime.utcnow()
                loc_log.patrol_unit_id = unit.id

        await db.commit()

        # Check if officer or patrol unit is actively responding to an SOS emergency
        active_sos_stmt = select(SOSRequest).where(
            and_(
                or_(
                    SOSRequest.assigned_officer_id == officer.id,
                    SOSRequest.assigned_patrol_id == (loc_log.patrol_unit_id if loc_log.patrol_unit_id else -1),
                ),
                SOSRequest.status.in_(["ASSIGNED", "ACCEPTED", "EN_ROUTE", "ARRIVED"]),
            )
        )
        active_sos_res = await db.execute(active_sos_stmt)
        active_sos_list = active_sos_res.scalars().all()

        location_service = LocationService.get_instance()
        for active_sos in active_sos_list:
            dist_km = round(
                location_service.haversine_distance(
                    active_sos.latitude,
                    active_sos.longitude,
                    latitude,
                    longitude,
                ),
                2,
            )
            await live_sos_manager.broadcast_location_telemetry(
                sos_id=active_sos.id,
                approximate_distance_km=dist_km,
                police_latitude=latitude,
                police_longitude=longitude,
            )

        return {
            "status": "success",
            "officer_id": officer.id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": datetime.utcnow().isoformat(),
        }



patrol_service = PatrolService.get_instance()

