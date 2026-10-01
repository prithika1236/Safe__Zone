"""SafeZone Geospatial Coverage Matrix Computation.

Calculates the bipartite coverage relations between candidate patrol locations
and spatial risk demand points within a configurable coverage radius (default 3.0 km).
"""

from typing import List, Dict, Any, Set
from pydantic import BaseModel, Field

from app.services.location_service import location_service
from app.optimization.candidate_generator import CandidateLocation, DemandPoint


class CoverageMatrix(BaseModel):
    """Bipartite coverage mapping between candidates and demand points."""
    coverage_radius_km: float
    candidate_to_demands: Dict[int, List[int]] = Field(default_factory=dict)
    demand_to_candidates: Dict[int, List[int]] = Field(default_factory=dict)
    total_demand_count: int = 0
    total_demand_weight: float = 0.0
    coverable_demand_count: int = 0
    coverable_demand_weight: float = 0.0


class CoverageService:
    """Computes spatial coverage matrices using True Great-Circle Haversine distance."""

    @staticmethod
    def build_coverage_matrix(
        candidates: List[CandidateLocation],
        demand_points: List[DemandPoint],
        coverage_radius_km: float = 3.0,
    ) -> CoverageMatrix:
        """Construct coverage mapping between candidate PRPs and demand points."""
        candidate_to_demands: Dict[int, List[int]] = {c.candidate_id: [] for c in candidates}
        demand_to_candidates: Dict[int, List[int]] = {dp.point_id: [] for dp in demand_points}

        total_weight = sum(dp.weight for dp in demand_points)
        covered_points_set: Set[int] = set()
        covered_weight = 0.0

        for cand in candidates:
            for dp in demand_points:
                dist = location_service.haversine_distance(
                    cand.latitude, cand.longitude, dp.latitude, dp.longitude
                )
                if dist <= coverage_radius_km:
                    candidate_to_demands[cand.candidate_id].append(dp.point_id)
                    demand_to_candidates[dp.point_id].append(cand.candidate_id)
                    if dp.point_id not in covered_points_set:
                        covered_points_set.add(dp.point_id)
                        covered_weight += dp.weight

        return CoverageMatrix(
            coverage_radius_km=coverage_radius_km,
            candidate_to_demands=candidate_to_demands,
            demand_to_candidates=demand_to_candidates,
            total_demand_count=len(demand_points),
            total_demand_weight=round(total_weight, 4),
            coverable_demand_count=len(covered_points_set),
            coverable_demand_weight=round(covered_weight, 4),
        )


coverage_service = CoverageService()
