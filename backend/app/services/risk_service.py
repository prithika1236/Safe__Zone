"""SafeZone Risk Service.

Coordinates spatial database queries, multi-factor risk computation,
cohort normalization across all 200 Chennai wards, and map GeoJSON generation.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crime import CrimeIncident
from app.models.optimization import RiskScore
from app.optimization.risk_scoring import (
    risk_scoring_engine,
    IncidentInput,
    RiskBreakdown,
)
from app.services.location_service import location_service
from app.schemas.risk import (
    WardRiskAssessment,
    WardRiskListResponse,
    PointRiskAssessment,
    RiskGeoJSONResponse,
)
from app.core.logging import logger


class RiskService:
    _instance: Optional["RiskService"] = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> "RiskService":
        if cls._instance is None:
            cls._instance = RiskService()
        return cls._instance

    async def calculate_ward_risks(
        self,
        db: AsyncSession,
        mode: str = "DYNAMIC",
        time_period: str = "ALL",
        reference_date: Optional[date] = None,
        lambda_val: Optional[float] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        save_to_db: bool = False,
    ) -> List[WardRiskAssessment]:
        """Compute multi-factor risk for all 200 Chennai wards with cohort normalization."""
        mode_upper = str(mode).upper()
        ref_date = reference_date or date.today()

        # Build query for incidents
        stmt = select(CrimeIncident)

        if start_date:
            stmt = stmt.where(CrimeIncident.occurred_date >= start_date)
        if end_date:
            stmt = stmt.where(CrimeIncident.occurred_date <= end_date)

        # In DYNAMIC mode without explicit start date, prioritize recent window (e.g. past 180 days)
        if mode_upper == "DYNAMIC" and not start_date:
            dynamic_cutoff = ref_date - timedelta(days=180)
            # Query recent incidents
            stmt = stmt.where(CrimeIncident.occurred_date >= dynamic_cutoff)

        result = await db.execute(stmt)
        incidents = result.scalars().all()

        # Group incidents by ward_no
        ward_incidents: Dict[int, List[IncidentInput]] = {}
        for inc in incidents:
            if inc.ward_no not in ward_incidents:
                ward_incidents[inc.ward_no] = []
            ward_incidents[inc.ward_no].append(
                IncidentInput(
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
            )

        # Score every known ward from LocationService
        all_wards = location_service.get_all_wards_metadata()
        breakdown_map: Dict[int, RiskBreakdown] = {}

        for w_meta in all_wards:
            w_no = w_meta["ward_no"]
            inc_list = ward_incidents.get(w_no, [])
            breakdown = risk_scoring_engine.compute_risk_for_incidents(
                incidents=inc_list,
                mode=mode_upper,
                reference_date=ref_date,
                target_shift=time_period,
                lambda_val=lambda_val,
            )
            breakdown_map[w_no] = breakdown

        # Normalize cohort scores across all wards
        risk_scoring_engine.normalize_cohort_scores(breakdown_map)

        # Build final assessment list
        assessments: List[WardRiskAssessment] = []
        for w_meta in all_wards:
            w_no = w_meta["ward_no"]
            b = breakdown_map[w_no]

            assessment = WardRiskAssessment(
                ward_no=w_no,
                zone_no=w_meta["zone_no"],
                zone_name=w_meta["zone_name"],
                mode=mode_upper,
                time_period=time_period,
                raw_risk_score=b.raw_score,
                normalized_risk_score=b.normalized_score,
                risk_level=b.risk_level,
                incident_count=b.incident_count,
                frequency_component=b.frequency_component,
                severity_component=b.severity_component,
                recency_component=b.recency_component,
                time_component=b.time_component,
                dominant_category=b.dominant_category,
                category_counts=b.category_counts,
                centroid_lat=w_meta.get("centroid_lat"),
                centroid_lon=w_meta.get("centroid_lon"),
            )
            assessments.append(assessment)

            # Persist to database if requested
            if save_to_db:
                risk_record = RiskScore(
                    ward_no=w_no,
                    zone_no=w_meta["zone_no"],
                    risk_type=mode_upper,
                    base_risk=b.normalized_score,
                    time_period=time_period,
                    calculated_at=datetime.utcnow(),
                    details={
                        "raw_score": b.raw_score,
                        "risk_level": b.risk_level,
                        "incident_count": b.incident_count,
                        "dominant_category": b.dominant_category,
                        "frequency_component": b.frequency_component,
                        "severity_component": b.severity_component,
                        "recency_component": b.recency_component,
                        "time_component": b.time_component,
                    },
                )
                db.add(risk_record)

        if save_to_db:
            await db.commit()

        # Sort assessments by descending risk score
        assessments.sort(key=lambda a: a.normalized_risk_score, reverse=True)
        return assessments

    async def get_ward_risk_by_number(
        self,
        db: AsyncSession,
        ward_no: int,
        mode: str = "DYNAMIC",
        time_period: str = "ALL",
        reference_date: Optional[date] = None,
        lambda_val: Optional[float] = None,
    ) -> WardRiskAssessment:
        """Get risk assessment for a specific ward."""
        all_risks = await self.calculate_ward_risks(
            db=db,
            mode=mode,
            time_period=time_period,
            reference_date=reference_date,
            lambda_val=lambda_val,
        )
        for r in all_risks:
            if r.ward_no == ward_no:
                return r

        # If ward not in metadata, return fallback empty assessment
        return WardRiskAssessment(
            ward_no=ward_no,
            zone_no="UNKNOWN",
            zone_name="UNKNOWN",
            mode=mode,
            time_period=time_period,
            raw_risk_score=0.0,
            normalized_risk_score=0.0,
            risk_level="LOW",
            incident_count=0,
            frequency_component=0.0,
            severity_component=0.0,
            recency_component=0.0,
            time_component=0.0,
            dominant_category="NONE",
            category_counts={},
        )

    async def calculate_point_risk(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        radius_km: float = 1.5,
        mode: str = "DYNAMIC",
        time_period: str = "ALL",
        reference_date: Optional[date] = None,
        lambda_val: Optional[float] = None,
    ) -> PointRiskAssessment:
        """Calculate spatial risk at any arbitrary (latitude, longitude) coordinate."""
        mode_upper = str(mode).upper()
        ref_date = reference_date or date.today()

        # Fetch incidents
        stmt = select(CrimeIncident)
        if mode_upper == "DYNAMIC":
            dynamic_cutoff = ref_date - timedelta(days=180)
            stmt = stmt.where(CrimeIncident.occurred_date >= dynamic_cutoff)

        result = await db.execute(stmt)
        all_incidents = result.scalars().all()

        # Filter incidents within radius_km using true Haversine distance
        nearby_inputs: List[IncidentInput] = []
        for inc in all_incidents:
            dist = location_service.haversine_distance(latitude, longitude, inc.latitude, inc.longitude)
            if dist <= radius_km:
                nearby_inputs.append(
                    IncidentInput(
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
                )

        breakdown = risk_scoring_engine.compute_risk_for_incidents(
            incidents=nearby_inputs,
            mode=mode_upper,
            reference_date=ref_date,
            target_shift=time_period,
            lambda_val=lambda_val,
        )

        # Categorize risk level from raw score (for localized points)
        if breakdown.raw_score <= 1.5:
            r_level = "LOW"
        elif breakdown.raw_score <= 5.0:
            r_level = "MEDIUM"
        elif breakdown.raw_score <= 12.0:
            r_level = "HIGH"
        else:
            r_level = "CRITICAL"

        # Determine containing ward
        ward_meta = location_service.find_ward_for_coordinate(latitude, longitude)

        return PointRiskAssessment(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            mode=mode_upper,
            time_period=time_period,
            ward_no=ward_meta["ward_no"] if ward_meta else None,
            zone_no=ward_meta["zone_no"] if ward_meta else None,
            zone_name=ward_meta["zone_name"] if ward_meta else None,
            raw_risk_score=breakdown.raw_score,
            risk_level=r_level,
            incident_count=breakdown.incident_count,
            frequency_component=breakdown.frequency_component,
            severity_component=breakdown.severity_component,
            recency_component=breakdown.recency_component,
            time_component=breakdown.time_component,
            dominant_category=breakdown.dominant_category,
            category_counts=breakdown.category_counts,
        )

    async def generate_risk_geojson(
        self,
        db: AsyncSession,
        mode: str = "DYNAMIC",
        time_period: str = "ALL",
        reference_date: Optional[date] = None,
        lambda_val: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate GeoJSON FeatureCollection with embedded risk properties for map rendering."""
        assessments = await self.calculate_ward_risks(
            db=db,
            mode=mode,
            time_period=time_period,
            reference_date=reference_date,
            lambda_val=lambda_val,
        )
        risk_map = {a.ward_no: a.model_dump() for a in assessments}
        return location_service.format_risk_geojson(risk_map)


risk_service = RiskService.get_instance()
