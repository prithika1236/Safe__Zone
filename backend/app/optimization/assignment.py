"""SafeZone Patrol Unit and Officer Assignment Optimization Engine.

Solves the optimal bipartite matching of available patrol units and police officers
to unassigned active/approved Patrol Response Points (PRPs).
Minimizes travel dispatch distance from unit locations to target PRPs
while strictly preventing incompatible duplicate assignments.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field
from ortools.linear_solver import pywraplp

from app.services.location_service import location_service


class AssignmentCandidateUnit(BaseModel):
    """Available patrol unit input for assignment solver."""
    unit_id: int
    unit_code: str
    unit_type: str = "VEHICLE"
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    is_available: bool = True


class AssignmentCandidateOfficer(BaseModel):
    """Available police officer input for assignment solver."""
    officer_id: int
    badge_number: str
    rank: str
    station_name: str
    on_duty: bool = True
    is_available: bool = True


class AssignmentTargetPRP(BaseModel):
    """Target Patrol Response Point to be assigned."""
    prp_id: int
    rank: int
    latitude: float
    longitude: float
    ward_no: int
    zone_no: str
    zone_name: str
    risk_score: float
    coverage_radius_km: float = 3.0


class MatchedAssignment(BaseModel):
    """Computed assignment match."""
    prp_id: int
    patrol_unit_id: int
    officer_id: int
    dispatch_distance_km: float
    prp_rank: int


class AssignmentSolverResult(BaseModel):
    """Result of optimization assignment run."""
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, NO_RESOURCES
    total_target_prps: int
    assigned_count: int
    unassigned_prp_ids: List[int] = Field(default_factory=list)
    matches: List[MatchedAssignment] = Field(default_factory=list)


class PatrolAssignmentEngine:
    """Mathematical assignment engine for optimal PRP patrol deployment."""

    # Default Chennai Police HQ reference coordinates if vehicle GPS is not yet logged
    DEFAULT_BASE_LAT = 13.0827
    DEFAULT_BASE_LON = 80.2707

    def solve_assignment(
        self,
        target_prps: List[AssignmentTargetPRP],
        available_units: List[AssignmentCandidateUnit],
        available_officers: List[AssignmentCandidateOfficer],
        busy_unit_ids: Optional[Set[int]] = None,
        busy_officer_ids: Optional[Set[int]] = None,
    ) -> AssignmentSolverResult:
        """Solve minimum-distance assignment matching units & officers to priority PRPs.
        
        Uses Google OR-Tools MIP solver with strict 1-to-1 capacity constraints.
        Prevents duplicate assignment of units/officers.
        """
        busy_units = busy_unit_ids or set()
        busy_officers = busy_officer_ids or set()

        # Filter strictly eligible units and officers
        eligible_units = [u for u in available_units if u.is_available and u.unit_id not in busy_units]
        eligible_officers = [o for o in available_officers if o.on_duty and o.is_available and o.officer_id not in busy_officers]

        total_prps = len(target_prps)

        # Edge cases: No PRPs or no available resources
        if total_prps == 0:
            return AssignmentSolverResult(
                status="OPTIMAL",
                total_target_prps=0,
                assigned_count=0,
                unassigned_prp_ids=[],
                matches=[],
            )

        if not eligible_units or not eligible_officers:
            return AssignmentSolverResult(
                status="NO_RESOURCES",
                total_target_prps=total_prps,
                assigned_count=0,
                unassigned_prp_ids=[p.prp_id for p in target_prps],
                matches=[],
            )

        # Sort PRPs by priority rank (Rank 1 first)
        sorted_prps = sorted(target_prps, key=lambda p: p.rank)

        # Maximum number of assignments is bounded by available resources
        max_possible = min(len(sorted_prps), len(eligible_units), len(eligible_officers))
        active_prp_subset = sorted_prps[:max_possible]

        # Formulate OR-Tools Minimum Distance Bipartite Matching for Units -> PRPs
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("CBC") or pywraplp.Solver.CreateSolver("GLOP")

        # x[u, p] in {0, 1}: unit u assigned to PRP p
        x_vars: Dict[Tuple[int, int], Any] = {}
        dist_matrix: Dict[Tuple[int, int], float] = {}

        for u in eligible_units:
            u_lat = u.current_latitude if u.current_latitude is not None else self.DEFAULT_BASE_LAT
            u_lon = u.current_longitude if u.current_longitude is not None else self.DEFAULT_BASE_LON
            for p in active_prp_subset:
                var = solver.BoolVar(f"x_{u.unit_id}_{p.prp_id}")
                x_vars[(u.unit_id, p.prp_id)] = var
                dist = location_service.haversine_distance(u_lat, u_lon, p.latitude, p.longitude)
                dist_matrix[(u.unit_id, p.prp_id)] = dist

        # Constraint 1: Each unit assigned to at most 1 PRP
        for u in eligible_units:
            solver.Add(solver.Sum(x_vars[(u.unit_id, p.prp_id)] for p in active_prp_subset) <= 1)

        # Constraint 2: Each PRP receives at most 1 unit
        for p in active_prp_subset:
            solver.Add(solver.Sum(x_vars[(u.unit_id, p.prp_id)] for u in eligible_units) <= 1)

        # Constraint 3: Maximize number of assigned PRPs (equal to max_possible)
        solver.Add(solver.Sum(x_vars[(u.unit_id, p.prp_id)] for u in eligible_units for p in active_prp_subset) == max_possible)

        # Objective: Minimize total dispatch distance
        objective = solver.Objective()
        for (u_id, p_id), var in x_vars.items():
            objective.SetCoefficient(var, float(dist_matrix[(u_id, p_id)]))
        objective.SetMinimization()

        solver_status = solver.Solve()

        matches: List[MatchedAssignment] = []
        assigned_prp_ids: Set[int] = set()

        if solver_status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            # Pair each matched (PRP, Unit) with an eligible officer
            matched_pairs = []
            for (u_id, p_id), var in x_vars.items():
                if var.solution_value() > 0.5:
                    prp_obj = next(p for p in active_prp_subset if p.prp_id == p_id)
                    matched_pairs.append((prp_obj, u_id, dist_matrix[(u_id, p_id)]))

            # Sort matched pairs by PRP rank
            matched_pairs.sort(key=lambda item: item[0].rank)

            for idx, (prp_obj, u_id, dist) in enumerate(matched_pairs):
                officer = eligible_officers[idx]
                matches.append(
                    MatchedAssignment(
                        prp_id=prp_obj.prp_id,
                        patrol_unit_id=u_id,
                        officer_id=officer.officer_id,
                        dispatch_distance_km=round(dist, 3),
                        prp_rank=prp_obj.rank,
                    )
                )
                assigned_prp_ids.add(prp_obj.prp_id)

            unassigned_ids = [p.prp_id for p in sorted_prps if p.prp_id not in assigned_prp_ids]
            return AssignmentSolverResult(
                status="OPTIMAL" if solver_status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
                total_target_prps=total_prps,
                assigned_count=len(matches),
                unassigned_prp_ids=unassigned_ids,
                matches=matches,
            )
        else:
            # Fallback Greedy matching if MIP solver encounters infeasibility
            for idx, prp_obj in enumerate(active_prp_subset):
                u = eligible_units[idx]
                o = eligible_officers[idx]
                u_lat = u.current_latitude if u.current_latitude is not None else self.DEFAULT_BASE_LAT
                u_lon = u.current_longitude if u.current_longitude is not None else self.DEFAULT_BASE_LON
                dist = location_service.haversine_distance(u_lat, u_lon, prp_obj.latitude, prp_obj.longitude)
                matches.append(
                    MatchedAssignment(
                        prp_id=prp_obj.prp_id,
                        patrol_unit_id=u.unit_id,
                        officer_id=o.officer_id,
                        dispatch_distance_km=round(dist, 3),
                        prp_rank=prp_obj.rank,
                    )
                )
                assigned_prp_ids.add(prp_obj.prp_id)

            unassigned_ids = [p.prp_id for p in sorted_prps if p.prp_id not in assigned_prp_ids]
            return AssignmentSolverResult(
                status="FEASIBLE",
                total_target_prps=total_prps,
                assigned_count=len(matches),
                unassigned_prp_ids=unassigned_ids,
                matches=matches,
            )


patrol_assignment_engine = PatrolAssignmentEngine()
