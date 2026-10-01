"""SafeZone PRP Optimization Service.

Coordinates incident extraction, demand point weighting, candidate generation,
Google OR-Tools solver execution, and database persistence for patrol deployments.
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import CrimeIncident
from app.models.optimization import OptimizationRun, PRPLocation
from app.optimization.candidate_generator import (
    candidate_generator,
    CandidateLocation,
    DemandPoint,
)
from app.optimization.prp_optimizer import prp_optimizer, OptimizationResult
from app.optimization.risk_scoring import risk_scoring_engine, IncidentInput
from app.schemas.prp import (
    PRPOptimizationRequest,
    PRPOptimizationResponse,
    PRPLocationResponse,
    OptimizationRunSummary,
)
from app.core.logging import logger


class PRPService:
    _instance: Optional["PRPService"] = None

    @classmethod
    def get_instance(cls) -> "PRPService":
        if cls._instance is None:
            cls._instance = PRPService()
        return cls._instance

    async def run_optimization(
        self,
        db: AsyncSession,
        request: PRPOptimizationRequest,
    ) -> PRPOptimizationResponse:
        """Execute PRP optimization workflow and optionally persist results."""
        mode_upper = str(request.mode).upper()
        ref_date = date.today()

        # 1. Query incidents based on mode and date constraints
        stmt = select(CrimeIncident)

        if request.start_date:
            stmt = stmt.where(CrimeIncident.occurred_date >= request.start_date)
        if request.end_date:
            stmt = stmt.where(CrimeIncident.occurred_date <= request.end_date)

        # In DYNAMIC mode without explicit start_date, focus on recent incidents
        if mode_upper == "DYNAMIC" and not request.start_date:
            dynamic_cutoff = ref_date - timedelta(days=180)
            stmt = stmt.where(CrimeIncident.occurred_date >= dynamic_cutoff)

        result = await db.execute(stmt)
        incidents = result.scalars().all()

        # 2. Build weighted DemandPoints using RiskScoringEngine
        demand_points: List[DemandPoint] = []
        for idx, inc in enumerate(incidents, start=1):
            inc_input = IncidentInput(
                crime_category=inc.crime_category,
                severity=inc.severity,
                occurred_date=inc.occurred_date,
                occurred_time=inc.occurred_time,
                time_period=inc.time_period,
                latitude=inc.latitude,
                longitude=inc.longitude,
                ward_no=inc.ward_no,
                zone_no=inc.zone_no,
            )
            scored = risk_scoring_engine.score_single_incident(
                incident=inc_input,
                mode=mode_upper,
                reference_date=ref_date,
                target_shift=request.time_period,
                lambda_val=request.lambda_val,
            )
            demand_points.append(
                DemandPoint(
                    point_id=idx,
                    latitude=inc.latitude,
                    longitude=inc.longitude,
                    weight=round(scored["total_contribution"], 4),
                    ward_no=inc.ward_no,
                    crime_category=inc.crime_category,
                    severity=inc.severity,
                )
            )

        # 3. Generate candidate patrol locations
        candidates: List[CandidateLocation] = candidate_generator.generate_candidates(
            demand_points=demand_points,
            min_separation_km=0.8,
        )

        # 4. Solve Maximum Coverage Optimization using Google OR-Tools
        opt_result: OptimizationResult = prp_optimizer.optimize(
            candidates=candidates,
            demand_points=demand_points,
            patrol_count=request.patrol_count,
            coverage_radius_km=request.coverage_radius_km,
            mode=mode_upper,
        )

        # Convert selected PRPs to response schema
        response_prps: List[PRPLocationResponse] = []
        for sp in opt_result.selected_prps:
            response_prps.append(
                PRPLocationResponse(
                    rank=sp.rank,
                    prp_type=sp.prp_type,
                    latitude=sp.latitude,
                    longitude=sp.longitude,
                    ward_no=sp.ward_no,
                    zone_no=sp.zone_no,
                    zone_name=sp.zone_name,
                    risk_score=sp.risk_score,
                    coverage_radius_km=sp.coverage_radius_km,
                    status="RECOMMENDED",
                    covered_demand_count=sp.covered_demand_count,
                    created_at=datetime.utcnow(),
                )
            )

        saved_run_id: Optional[int] = None

        # 5. Persist run and PRPs if requested
        if request.save_run:
            run_record = OptimizationRun(
                run_type=mode_upper,
                parameters={
                    "mode": mode_upper,
                    "patrol_count": request.patrol_count,
                    "coverage_radius_km": request.coverage_radius_km,
                    "time_period": request.time_period,
                    "lambda_val": request.lambda_val,
                    "start_date": str(request.start_date) if request.start_date else None,
                    "end_date": str(request.end_date) if request.end_date else None,
                },
                total_prps_generated=len(response_prps),
                status=opt_result.status,
                execution_time_seconds=opt_result.execution_time_seconds,
            )
            db.add(run_record)
            await db.flush()
            saved_run_id = run_record.id

            for sp, resp_prp in zip(opt_result.selected_prps, response_prps):
                prp_record = PRPLocation(
                    optimization_run_id=saved_run_id,
                    prp_type=mode_upper,
                    latitude=sp.latitude,
                    longitude=sp.longitude,
                    ward_no=sp.ward_no,
                    zone_no=sp.zone_no,
                    zone_name=sp.zone_name,
                    rank=sp.rank,
                    risk_score=sp.risk_score,
                    coverage_radius_km=sp.coverage_radius_km,
                    status="RECOMMENDED",
                )
                db.add(prp_record)
                await db.flush()
                resp_prp.id = prp_record.id
                resp_prp.optimization_run_id = saved_run_id

            await db.commit()

        return PRPOptimizationResponse(
            run_id=saved_run_id,
            run_type=opt_result.run_type,
            status=opt_result.status,
            execution_time_seconds=opt_result.execution_time_seconds,
            available_patrol_count=opt_result.available_patrol_count,
            coverage_radius_km=opt_result.coverage_radius_km,
            total_demand_points=opt_result.total_demand_points,
            total_weighted_risk=opt_result.total_weighted_risk,
            covered_demand_points=opt_result.covered_demand_points,
            covered_weighted_risk=opt_result.covered_weighted_risk,
            coverage_percentage=opt_result.coverage_percentage,
            uncovered_high_risk_points=opt_result.uncovered_high_risk_points,
            selected_prps=response_prps,
        )

    async def list_optimization_runs(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50,
    ) -> List[OptimizationRunSummary]:
        """List historical optimization runs with generated PRPs."""
        stmt = (
            select(OptimizationRun)
            .options(selectinload(OptimizationRun.prps))
            .order_by(desc(OptimizationRun.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        runs = result.scalars().all()

        summaries = []
        for r in runs:
            prp_list = [
                PRPLocationResponse(
                    id=p.id,
                    optimization_run_id=p.optimization_run_id,
                    rank=p.rank,
                    prp_type=p.prp_type,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    ward_no=p.ward_no,
                    zone_no=p.zone_no,
                    zone_name=p.zone_name,
                    risk_score=p.risk_score,
                    coverage_radius_km=p.coverage_radius_km,
                    status=p.status,
                    created_at=p.created_at,
                )
                for p in r.prps
            ]
            summaries.append(
                OptimizationRunSummary(
                    id=r.id,
                    run_type=r.run_type,
                    total_prps_generated=r.total_prps_generated,
                    status=r.status,
                    execution_time_seconds=r.execution_time_seconds,
                    parameters=r.parameters,
                    created_at=r.created_at,
                    prps=prp_list,
                )
            )
        return summaries

    async def get_optimization_run(
        self,
        db: AsyncSession,
        run_id: int,
    ) -> Optional[OptimizationRunSummary]:
        """Fetch details of a specific optimization run by ID."""
        stmt = (
            select(OptimizationRun)
            .options(selectinload(OptimizationRun.prps))
            .where(OptimizationRun.id == run_id)
        )
        result = await db.execute(stmt)
        r = result.scalar_one_or_none()
        if not r:
            return None

        prp_list = [
            PRPLocationResponse(
                id=p.id,
                optimization_run_id=p.optimization_run_id,
                rank=p.rank,
                prp_type=p.prp_type,
                latitude=p.latitude,
                longitude=p.longitude,
                ward_no=p.ward_no,
                zone_no=p.zone_no,
                zone_name=p.zone_name,
                risk_score=p.risk_score,
                coverage_radius_km=p.coverage_radius_km,
                status=p.status,
                created_at=p.created_at,
            )
            for p in r.prps
        ]
        return OptimizationRunSummary(
            id=r.id,
            run_type=r.run_type,
            total_prps_generated=r.total_prps_generated,
            status=r.status,
            execution_time_seconds=r.execution_time_seconds,
            parameters=r.parameters,
            created_at=r.created_at,
            prps=prp_list,
        )

    async def update_prp_status(
        self,
        db: AsyncSession,
        prp_id: int,
        new_status: str,
    ) -> Optional[PRPLocationResponse]:
        """Update deployment status of a PRP (RECOMMENDED, APPROVED, ACTIVE, REJECTED)."""
        stmt = select(PRPLocation).where(PRPLocation.id == prp_id)
        result = await db.execute(stmt)
        prp = result.scalar_one_or_none()
        if not prp:
            return None

        prp.status = new_status.upper()
        await db.commit()
        await db.refresh(prp)

        return PRPLocationResponse(
            id=prp.id,
            optimization_run_id=prp.optimization_run_id,
            rank=prp.rank,
            prp_type=prp.prp_type,
            latitude=prp.latitude,
            longitude=prp.longitude,
            ward_no=prp.ward_no,
            zone_no=prp.zone_no,
            zone_name=prp.zone_name,
            risk_score=prp.risk_score,
            coverage_radius_km=prp.coverage_radius_km,
            status=prp.status,
            created_at=prp.created_at,
        )

    async def list_active_prps(
        self,
        db: AsyncSession,
    ) -> List[PRPLocationResponse]:
        """Retrieve all currently active PRPs for patrol deployment."""
        stmt = select(PRPLocation).where(PRPLocation.status.in_(["ACTIVE", "APPROVED"])).order_by(PRPLocation.rank)
        result = await db.execute(stmt)
        active_prps = result.scalars().all()

        return [
            PRPLocationResponse(
                id=p.id,
                optimization_run_id=p.optimization_run_id,
                rank=p.rank,
                prp_type=p.prp_type,
                latitude=p.latitude,
                longitude=p.longitude,
                ward_no=p.ward_no,
                zone_no=p.zone_no,
                zone_name=p.zone_name,
                risk_score=p.risk_score,
                coverage_radius_km=p.coverage_radius_km,
                status=p.status,
                created_at=p.created_at,
            )
            for p in active_prps
        ]


prp_service = PRPService.get_instance()
