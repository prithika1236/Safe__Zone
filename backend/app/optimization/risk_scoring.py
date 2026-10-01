"""SafeZone Unified Risk Scoring and Optimization Engine.

Implements the single frozen risk scoring engine supporting:
- Multi-factor risk modeling: Frequency, Severity, Recency, Time-of-Day/Shift relevance
- Configurable recency decay: recency_weight = exp(-lambda * age_in_days)
- Explainable risk components (frequency, severity, recency, time contribution)
- Two operational modes:
    * REFERENCE mode: Historical long-term crime baseline without recency decay
    * DYNAMIC mode: Time-sensitive real-time operational risk with exponential recency & shift weighting
- Safe normalization across spatial boundaries (Min-Max to [0.0, 1.0])
- Graceful empty dataset handling
"""

import math
from datetime import date, datetime, time
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings


# Severity weights mapping
SEVERITY_WEIGHTS: Dict[str, float] = {
    "HIGH": 3.0,
    "MEDIUM": 2.0,
    "LOW": 1.0,
}

# Category-specific base severity factors
CATEGORY_SEVERITY_FACTORS: Dict[str, float] = {
    "HOMICIDE": 3.5,
    "KIDNAPPING": 3.2,
    "ROBBERY": 3.0,
    "ASSAULT": 2.8,
    "SEXUAL_HARASSMENT": 2.8,
    "BURGLARY": 2.5,
    "DOMESTIC_VIOLENCE": 2.5,
    "DRUG_RELATED_CRIME": 2.2,
    "CYBERCRIME": 2.0,
    "FRAUD": 2.0,
    "THEFT": 1.8,
    "STALKING": 1.8,
    "PUBLIC_DISTURBANCE": 1.4,
    "VANDALISM": 1.2,
    "VERBAL_ABUSE_THREAT": 1.2,
    "OTHER": 1.0,
}

SHIFT_WINDOWS: Dict[str, Tuple[int, int]] = {
    "MORNING": (6, 12),
    "AFTERNOON": (12, 18),
    "EVENING": (18, 22),
    "NIGHT": (22, 6),
}


class IncidentInput(BaseModel):
    """Normalized incident representation for risk scoring engine."""
    crime_category: str
    severity: str = "MEDIUM"
    occurred_date: date
    occurred_time: Optional[time] = None
    time_period: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ward_no: Optional[int] = None
    zone_no: Optional[str] = None


class RiskBreakdown(BaseModel):
    """Explainable components of computed risk score."""
    incident_count: int = 0
    raw_score: float = 0.0
    normalized_score: float = 0.0
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    frequency_component: float = 0.0
    severity_component: float = 0.0
    recency_component: float = 0.0
    time_component: float = 0.0
    dominant_category: str = "NONE"
    category_counts: Dict[str, int] = Field(default_factory=dict)


class RiskScoringEngine:
    """Unified SafeZone Risk Calculation Engine."""

    def __init__(
        self,
        default_lambda: float = 0.05,
        default_coverage_radius_km: float = 3.0,
    ):
        self.default_lambda = default_lambda
        self.default_coverage_radius_km = default_coverage_radius_km

    @staticmethod
    def calculate_recency_weight(
        occurred_date: date,
        reference_date: Optional[date] = None,
        lambda_val: float = 0.05,
    ) -> float:
        """Calculate exponential recency decay: exp(-lambda * age_in_days)."""
        if lambda_val <= 0.0:
            return 1.0

        ref = reference_date or date.today()
        age_in_days = max(0, (ref - occurred_date).days)
        return math.exp(-lambda_val * age_in_days)

    @staticmethod
    def calculate_severity_weight(severity: str, category: Optional[str] = None) -> float:
        """Calculate combined severity multiplier from severity grade and category."""
        base_sev = SEVERITY_WEIGHTS.get(str(severity).upper(), 2.0)
        cat_sev = CATEGORY_SEVERITY_FACTORS.get(str(category).upper(), 1.0) if category else 1.0
        # Blended severity score
        return base_sev * (0.7 + 0.3 * (cat_sev / 3.0))

    @staticmethod
    def calculate_time_relevance_weight(
        incident_time_period: Optional[str],
        target_shift: str = "ALL",
    ) -> float:
        """Calculate time/shift relevance multiplier."""
        target = str(target_shift).upper()
        if target in ["ALL", "", "NONE", None]:
            return 1.0

        inc_period = str(incident_time_period).upper() if incident_time_period else "ALL"
        if inc_period == target:
            return 1.5
        elif inc_period == "ALL":
            return 1.0
        else:
            return 0.5  # Non-matching shift attenuation

    def score_single_incident(
        self,
        incident: IncidentInput,
        mode: str = "DYNAMIC",
        reference_date: Optional[date] = None,
        target_shift: str = "ALL",
        lambda_val: Optional[float] = None,
    ) -> Dict[str, float]:
        """Compute the multi-factor contribution of a single incident."""
        mode_upper = str(mode).upper()
        effective_lambda = 0.0 if mode_upper == "REFERENCE" else (lambda_val if lambda_val is not None else self.default_lambda)

        sev_weight = self.calculate_severity_weight(incident.severity, incident.crime_category)
        rec_weight = self.calculate_recency_weight(incident.occurred_date, reference_date, effective_lambda)
        time_weight = self.calculate_time_relevance_weight(incident.time_period, target_shift)

        total_contribution = sev_weight * rec_weight * time_weight

        return {
            "total_contribution": total_contribution,
            "severity_weight": sev_weight,
            "recency_weight": rec_weight,
            "time_weight": time_weight,
        }

    def compute_risk_for_incidents(
        self,
        incidents: List[IncidentInput],
        mode: str = "DYNAMIC",
        reference_date: Optional[date] = None,
        target_shift: str = "ALL",
        lambda_val: Optional[float] = None,
        historical_baseline_score: Optional[float] = None,
    ) -> RiskBreakdown:
        """Compute aggregate risk and explainable components for a set of incidents."""
        n = len(incidents)
        if n == 0:
            return RiskBreakdown()

        mode_upper = str(mode).upper()
        effective_lambda = 0.0 if mode_upper == "REFERENCE" else (lambda_val if lambda_val is not None else self.default_lambda)

        total_raw = 0.0
        sum_sev = 0.0
        sum_rec = 0.0
        sum_time = 0.0
        cat_counts: Dict[str, int] = {}

        for inc in incidents:
            scored = self.score_single_incident(
                inc,
                mode=mode_upper,
                reference_date=reference_date,
                target_shift=target_shift,
                lambda_val=effective_lambda,
            )
            total_raw += scored["total_contribution"]
            sum_sev += scored["severity_weight"]
            sum_rec += scored["recency_weight"]
            sum_time += scored["time_weight"]

            cat = str(inc.crime_category).upper()
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        dominant_cat = max(cat_counts, key=cat_counts.get) if cat_counts else "NONE"

        # In DYNAMIC mode, blend with historical baseline if provided
        if mode_upper == "DYNAMIC" and historical_baseline_score is not None and historical_baseline_score > 0:
            blended_raw = 0.75 * total_raw + 0.25 * historical_baseline_score
        else:
            blended_raw = total_raw

        return RiskBreakdown(
            incident_count=n,
            raw_score=round(blended_raw, 4),
            normalized_score=0.0,  # Computed when normalizing across the cohort
            risk_level="LOW",
            frequency_component=float(n),
            severity_component=round(sum_sev / n, 4),
            recency_component=round(sum_rec / n, 4),
            time_component=round(sum_time / n, 4),
            dominant_category=dominant_cat,
            category_counts=cat_counts,
        )

    @staticmethod
    def normalize_cohort_scores(
        breakdowns: Dict[Any, RiskBreakdown],
    ) -> Dict[Any, RiskBreakdown]:
        """Normalize raw risk scores across all items in a cohort (e.g. all 200 wards).
        
        Applies Min-Max scaling to [0.0, 1.0] and assigns risk_level grades.
        """
        if not breakdowns:
            return {}

        raw_scores = [b.raw_score for b in breakdowns.values()]
        min_s = min(raw_scores)
        max_s = max(raw_scores)
        span = max_s - min_s

        for key, item in breakdowns.items():
            if span > 1e-6:
                norm = (item.raw_score - min_s) / span
            else:
                norm = 1.0 if item.raw_score > 0 else 0.0

            norm = max(0.0, min(1.0, norm))
            item.normalized_score = round(norm, 4)

            # Assign categorical risk level
            if norm < 0.25:
                item.risk_level = "LOW"
            elif norm < 0.55:
                item.risk_level = "MEDIUM"
            elif norm < 0.80:
                item.risk_level = "HIGH"
            else:
                item.risk_level = "CRITICAL"

        return breakdowns


risk_scoring_engine = RiskScoringEngine(
    default_lambda=settings.RISK_RECENCY_LAMBDA,
    default_coverage_radius_km=settings.DEFAULT_COVERAGE_RADIUS_KM,
)
