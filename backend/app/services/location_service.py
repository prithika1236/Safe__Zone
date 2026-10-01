"""SafeZone Location and Geospatial Service.

Provides robust geographic calculations:
- True Great-Circle Haversine distance in kilometers and meters
- Ward GeoJSON loading and caching
- Point-in-polygon ward resolution via Shapely
- Coverage radius calculations
- Map-ready GeoJSON feature and heatmap formatting
"""

import json
import math
import os
from typing import Dict, Any, List, Optional, Tuple
from shapely.geometry import shape, Point


class LocationService:
    _instance: Optional["LocationService"] = None

    # Earth radius in kilometers (WGS-84 mean radius)
    EARTH_RADIUS_KM = 6371.0088

    def __init__(self, geojson_path: Optional[str] = None):
        self.geojson_path = self._resolve_geojson_path(geojson_path)
        self.wards_geojson: Dict[str, Any] = {}
        self.ward_geometries: Dict[int, Any] = {}
        self.ward_metadata: Dict[int, Dict[str, Any]] = {}
        self._load_wards()

    @classmethod
    def get_instance(cls) -> "LocationService":
        if cls._instance is None:
            cls._instance = LocationService()
        return cls._instance

    @staticmethod
    def _resolve_geojson_path(target_path: Optional[str]) -> str:
        if target_path and os.path.exists(target_path):
            return target_path
        # Search common paths
        candidates = [
            "data/raw/Wards.geojson",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "Wards.geojson"),
            os.path.join(os.getcwd(), "data", "raw", "Wards.geojson"),
        ]
        for candidate in candidates:
            norm = os.path.normpath(candidate)
            if os.path.exists(norm):
                return norm
        return "data/raw/Wards.geojson"

    def _load_wards(self):
        """Load and parse Wards.geojson into in-memory spatial index."""
        if not os.path.exists(self.geojson_path):
            return

        with open(self.geojson_path, "r", encoding="utf-8") as f:
            self.wards_geojson = json.load(f)

        features = self.wards_geojson.get("features", [])
        for feat in features:
            props = feat.get("properties", {})
            geom_data = feat.get("geometry", {})
            try:
                ward_no = int(props.get("Ward_No"))
            except (ValueError, TypeError):
                continue

            geom = shape(geom_data)
            self.ward_geometries[ward_no] = geom

            centroid = geom.centroid
            self.ward_metadata[ward_no] = {
                "ward_no": ward_no,
                "zone_no": str(props.get("Zone_No", "")),
                "zone_name": str(props.get("Zone_Name", "")),
                "area": float(props.get("AREA", 0.0)),
                "perimeter": float(props.get("PERIMETER", 0.0)),
                "centroid_lat": centroid.y,
                "centroid_lon": centroid.x,
            }

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate Great-Circle distance between two coordinates in Kilometers.
        
        Uses the Haversine formula on spherical Earth geometry.
        Does NOT approximate degrees as kilometers.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return LocationService.EARTH_RADIUS_KM * c

    @staticmethod
    def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate Great-Circle distance in Meters."""
        return LocationService.haversine_distance(lat1, lon1, lat2, lon2) * 1000.0

    def find_ward_for_coordinate(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Find the Chennai ward containing a specific (latitude, longitude) coordinate.
        
        Returns metadata dictionary if inside, or None.
        """
        point = Point(longitude, latitude)  # Shapely uses (x=lon, y=lat)
        for ward_no, geom in self.ward_geometries.items():
            if geom.contains(point):
                return self.ward_metadata.get(ward_no)

        # Fallback to intersects (touching boundary)
        for ward_no, geom in self.ward_geometries.items():
            if geom.intersects(point):
                return self.ward_metadata.get(ward_no)

        return None

    def get_ward_metadata(self, ward_no: int) -> Optional[Dict[str, Any]]:
        """Retrieve metadata and centroid for a specific ward number."""
        return self.ward_metadata.get(ward_no)

    def get_all_wards_metadata(self) -> List[Dict[str, Any]]:
        """Get sorted list of all 200 wards metadata."""
        return [self.ward_metadata[w] for w in sorted(self.ward_metadata.keys())]

    def get_points_within_radius(
        self,
        center_lat: float,
        center_lon: float,
        points: List[Tuple[float, float]],
        radius_km: float,
    ) -> List[int]:
        """Return indices of coordinates that lie within radius_km from center."""
        covered_indices = []
        for idx, (lat, lon) in enumerate(points):
            dist = self.haversine_distance(center_lat, center_lon, lat, lon)
            if dist <= radius_km:
                covered_indices.append(idx)
        return covered_indices

    def format_risk_geojson(self, ward_risk_map: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate GeoJSON FeatureCollection enriched with calculated risk metrics."""
        features = []
        raw_features = self.wards_geojson.get("features", [])

        for feat in raw_features:
            props = feat.get("properties", {}).copy()
            try:
                ward_no = int(props.get("Ward_No"))
            except (ValueError, TypeError):
                continue

            risk_info = ward_risk_map.get(ward_no, {
                "raw_risk_score": 0.0,
                "normalized_risk_score": 0.0,
                "risk_level": "LOW",
                "incident_count": 0,
                "dominant_category": "NONE",
            })

            props.update({
                "raw_risk_score": risk_info.get("raw_risk_score", 0.0),
                "normalized_risk_score": risk_info.get("normalized_risk_score", 0.0),
                "risk_level": risk_info.get("risk_level", "LOW"),
                "incident_count": risk_info.get("incident_count", 0),
                "dominant_category": risk_info.get("dominant_category", "NONE"),
            })

            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": feat.get("geometry"),
            })

        return {
            "type": "FeatureCollection",
            "crs": self.wards_geojson.get("crs", {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}),
            "features": features,
        }


location_service = LocationService.get_instance()
