"""SafeZone PRP Candidate Location Generator.

Generates sensible, deduplicated candidate patrol response point (PRP) locations
from geospatial ward structures and crime/risk density hotspots.
Prevents naive 1-to-1 mapping of every single crime coordinate into a patrol post.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from app.services.location_service import location_service


class CandidateLocation(BaseModel):
    """PRP Candidate Location Representation."""
    candidate_id: int
    latitude: float
    longitude: float
    ward_no: int
    zone_no: str
    zone_name: str
    source_type: str = "WARD_CENTROID"  # WARD_CENTROID, HOTSPOT_CENTER, GRID_ANCHOR


class DemandPoint(BaseModel):
    """Spatial Demand Point with Risk Weight."""
    point_id: int
    latitude: float
    longitude: float
    weight: float = 1.0
    ward_no: Optional[int] = None
    crime_category: Optional[str] = None
    severity: Optional[str] = None


class CandidateGenerator:
    """Generates and deduplicates candidate patrol locations."""

    def __init__(self, min_separation_km: float = 0.8):
        self.min_separation_km = min_separation_km

    def generate_candidates(
        self,
        demand_points: List[DemandPoint],
        target_ward_numbers: Optional[List[int]] = None,
        min_separation_km: Optional[float] = None,
        max_candidates: int = 150,
    ) -> List[CandidateLocation]:
        """Generate deduplicated candidate patrol positions from ward centroids and incident density."""
        separation_threshold = min_separation_km if min_separation_km is not None else self.min_separation_km
        raw_candidates: List[Tuple[float, float, str, Dict[str, Any], float]] = []

        # 1. Add Ward Centroids as primary positioning anchors
        all_wards = location_service.get_all_wards_metadata()
        for w in all_wards:
            w_no = w["ward_no"]
            if target_ward_numbers and w_no not in target_ward_numbers:
                continue

            lat = w.get("centroid_lat")
            lon = w.get("centroid_lon")
            if lat is not None and lon is not None:
                # Priority: base priority 10.0
                raw_candidates.append((lat, lon, "WARD_CENTROID", w, 10.0))

        # 2. Extract hotspot cluster centers from demand points
        if demand_points:
            # Group demand points into spatial bins (~0.01 deg ~= 1.1 km)
            grid_bins: Dict[Tuple[int, int], List[DemandPoint]] = {}
            for dp in demand_points:
                grid_key = (round(dp.latitude * 100), round(dp.longitude * 100))
                if grid_key not in grid_bins:
                    grid_bins[grid_key] = []
                grid_bins[grid_key].append(dp)

            for grid_key, pts in grid_bins.items():
                if not pts or len(pts) < 2:  # Hotspot requires multiple incidents
                    continue

                total_weight = sum(p.weight for p in pts)
                if total_weight > 1e-6:
                    center_lat = sum(p.latitude * p.weight for p in pts) / total_weight
                    center_lon = sum(p.longitude * p.weight for p in pts) / total_weight
                else:
                    # Mathematically defensible unweighted geographic centroid for zero-weight clusters
                    n_pts = len(pts)
                    if n_pts > 0:
                        center_lat = sum(p.latitude for p in pts) / n_pts
                        center_lon = sum(p.longitude for p in pts) / n_pts
                    else:
                        continue

                ward_meta = location_service.find_ward_for_coordinate(center_lat, center_lon)
                if ward_meta:
                    raw_candidates.append(
                        (center_lat, center_lon, "HOTSPOT_CENTER", ward_meta, total_weight * 2.0)
                    )

        # 3. Sort raw candidates by priority / weight descending
        raw_candidates.sort(key=lambda item: item[4], reverse=True)

        # 4. Spatial Deduplication (Greedy distance thinning)
        accepted: List[CandidateLocation] = []
        candidate_idx = 1

        for lat, lon, source_type, meta, _ in raw_candidates:
            # Check if too close to already accepted candidate
            is_duplicate = False
            for acc in accepted:
                dist = location_service.haversine_distance(lat, lon, acc.latitude, acc.longitude)
                if dist < separation_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                accepted.append(
                    CandidateLocation(
                        candidate_id=candidate_idx,
                        latitude=round(lat, 6),
                        longitude=round(lon, 6),
                        ward_no=meta.get("ward_no", 0),
                        zone_no=meta.get("zone_no", ""),
                        zone_name=meta.get("zone_name", ""),
                        source_type=source_type,
                    )
                )
                candidate_idx += 1
                if len(accepted) >= max_candidates:
                    break

        return accepted


candidate_generator = CandidateGenerator()
