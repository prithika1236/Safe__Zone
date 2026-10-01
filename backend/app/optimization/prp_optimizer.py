"""SafeZone PRP Optimizer using Google OR-Tools.

Implements the single mathematical optimization engine for both
REFERENCE and DYNAMIC patrol response point (PRP) deployment.

Formulation (Maximum Coverage Location Problem - MCLP):
  Maximize: sum_{i} w_i * x_i  (UNIQUE weighted crime-risk coverage)
  Subject to:
    x_i <= sum_{j in N(i)} y_j    forall demand points i
    sum_{j} y_j <= available_patrol_count
    y_j, x_i in {0, 1}

Prevents double-counting when multiple PRPs cover the same demand point.
"""

import time
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from ortools.linear_solver import pywraplp

from app.optimization.candidate_generator import CandidateLocation, DemandPoint
from app.optimization.coverage import coverage_service, CoverageMatrix


class SelectedPRP(BaseModel):
    """Optimized Patrol Response Point Output."""
    rank: int
    candidate_id: int
    prp_type: str  # REFERENCE or DYNAMIC
    latitude: float
    longitude: float
    ward_no: int
    zone_no: str
    zone_name: str
    risk_score: float  # Marginal weighted risk covered
    coverage_radius_km: float
    covered_demand_count: int
    covered_demand_ids: List[int] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    """Complete PRP Optimization Output."""
    run_type: str  # REFERENCE or DYNAMIC
    status: str    # OPTIMAL, FEASIBLE, INFEASIBLE, NO_DATA
    execution_time_seconds: float
    available_patrol_count: int
    coverage_radius_km: float
    total_demand_points: int
    total_weighted_risk: float
    covered_demand_points: int
    covered_weighted_risk: float
    coverage_percentage: float
    uncovered_high_risk_points: int
    selected_prps: List[SelectedPRP] = Field(default_factory=list)


class PRPOptimizer:
    """Unified SafeZone PRP Optimization Engine."""

    def optimize(
        self,
        candidates: List[CandidateLocation],
        demand_points: List[DemandPoint],
        patrol_count: int = 10,
        coverage_radius_km: float = 3.0,
        mode: str = "DYNAMIC",
    ) -> OptimizationResult:
        """Solve Maximum Coverage Location Problem (MCLP) using Google OR-Tools MIP solver."""
        start_time = time.time()
        mode_upper = str(mode).upper()

        total_points = len(demand_points)
        total_weight = sum(dp.weight for dp in demand_points)

        # 1. Edge Case: No demand points (Zero crimes)
        if total_points == 0:
            exec_time = time.time() - start_time
            return OptimizationResult(
                run_type=mode_upper,
                status="NO_DATA",
                execution_time_seconds=round(exec_time, 4),
                available_patrol_count=patrol_count,
                coverage_radius_km=coverage_radius_km,
                total_demand_points=0,
                total_weighted_risk=0.0,
                covered_demand_points=0,
                covered_weighted_risk=0.0,
                coverage_percentage=0.0,
                uncovered_high_risk_points=0,
                selected_prps=[],
            )

        # 2. Edge Case: Zero patrol count requested
        if patrol_count <= 0 or not candidates:
            exec_time = time.time() - start_time
            return OptimizationResult(
                run_type=mode_upper,
                status="OPTIMAL",
                execution_time_seconds=round(exec_time, 4),
                available_patrol_count=patrol_count,
                coverage_radius_km=coverage_radius_km,
                total_demand_points=total_points,
                total_weighted_risk=round(total_weight, 4),
                covered_demand_points=0,
                covered_weighted_risk=0.0,
                coverage_percentage=0.0,
                uncovered_high_risk_points=sum(1 for dp in demand_points if dp.weight >= 2.0),
                selected_prps=[],
            )

        # 3. Compute Bipartite Coverage Matrix
        cov_matrix: CoverageMatrix = coverage_service.build_coverage_matrix(
            candidates=candidates,
            demand_points=demand_points,
            coverage_radius_km=coverage_radius_km,
        )

        # 4. Formulate OR-Tools MIP Model
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            # Fallback solver if SCIP not found
            solver = pywraplp.Solver.CreateSolver("CBC") or pywraplp.Solver.CreateSolver("GLOP")

        # Decision variables: y[j] for each candidate
        y_vars: Dict[int, Any] = {}
        for cand in candidates:
            y_vars[cand.candidate_id] = solver.BoolVar(f"y_{cand.candidate_id}")

        # Decision variables: x[i] for each demand point
        x_vars: Dict[int, Any] = {}
        demand_weight_map = {dp.point_id: dp.weight for dp in demand_points}
        for dp in demand_points:
            x_vars[dp.point_id] = solver.BoolVar(f"x_{dp.point_id}")

        # Constraint 1: Maximum patrol capacity constraint
        effective_capacity = min(patrol_count, len(candidates))
        solver.Add(solver.Sum(y_vars[c.candidate_id] for c in candidates) <= effective_capacity)

        # Constraint 2: Coverage constraints (x[i] <= sum_{j covering i} y[j])
        for dp_id, candidate_ids in cov_matrix.demand_to_candidates.items():
            if candidate_ids:
                solver.Add(x_vars[dp_id] <= solver.Sum(y_vars[cid] for cid in candidate_ids))
            else:
                solver.Add(x_vars[dp_id] == 0)

        # Objective: Maximize UNIQUE weighted demand coverage
        objective = solver.Objective()
        for dp_id, weight in demand_weight_map.items():
            objective.SetCoefficient(x_vars[dp_id], float(weight))
        objective.SetMaximization()

        # Solve
        solver_status = solver.Solve()

        status_str = "OPTIMAL"
        if solver_status == pywraplp.Solver.OPTIMAL:
            status_str = "OPTIMAL"
        elif solver_status == pywraplp.Solver.FEASIBLE:
            status_str = "FEASIBLE"
        else:
            status_str = "INFEASIBLE"

        # 5. Extract Selected PRPs and determine marginal contribution rankings
        chosen_candidate_ids: List[int] = [
            cid for cid, var in y_vars.items() if var.solution_value() > 0.5
        ]

        cand_map = {c.candidate_id: c for c in candidates}
        selected_prps: List[SelectedPRP] = []

        # Track unique coverage per PRP for explainable marginal ranking
        already_covered_demands: Set[int] = set()

        # Calculate marginal coverage for greedy ranking of selected PRPs
        unranked_chosen = []
        for cid in chosen_candidate_ids:
            covered_ids = cov_matrix.candidate_to_demands.get(cid, [])
            total_cand_weight = sum(demand_weight_map[pid] for pid in covered_ids)
            unranked_chosen.append((cid, total_cand_weight, covered_ids))

        # Sort selected PRPs by initial coverage weight descending
        unranked_chosen.sort(key=lambda item: item[1], reverse=True)

        rank = 1
        for cid, _, covered_ids in unranked_chosen:
            cand = cand_map[cid]
            # Marginal newly covered points
            new_covered = [pid for pid in covered_ids if pid not in already_covered_demands]
            already_covered_demands.update(new_covered)
            marginal_weight = sum(demand_weight_map[pid] for pid in new_covered)

            selected_prps.append(
                SelectedPRP(
                    rank=rank,
                    candidate_id=cid,
                    prp_type=mode_upper,
                    latitude=cand.latitude,
                    longitude=cand.longitude,
                    ward_no=cand.ward_no,
                    zone_no=cand.zone_no,
                    zone_name=cand.zone_name,
                    risk_score=round(marginal_weight if marginal_weight > 0 else sum(demand_weight_map[p] for p in covered_ids), 4),
                    coverage_radius_km=coverage_radius_km,
                    covered_demand_count=len(covered_ids),
                    covered_demand_ids=covered_ids,
                )
            )
            rank += 1

        # 6. Aggregate final coverage statistics
        covered_points_count = sum(1 for pid, var in x_vars.items() if var.solution_value() > 0.5)
        covered_risk_val = sum(
            demand_weight_map[pid] for pid, var in x_vars.items() if var.solution_value() > 0.5
        )

        cov_pct = (
            (covered_risk_val / total_weight * 100.0)
            if total_weight > 0
            else 0.0
        )

        uncovered_high_risk = sum(
            1 for pid, var in x_vars.items()
            if var.solution_value() < 0.5 and demand_weight_map.get(pid, 0.0) >= 2.0
        )

        exec_time = time.time() - start_time

        return OptimizationResult(
            run_type=mode_upper,
            status=status_str,
            execution_time_seconds=round(exec_time, 4),
            available_patrol_count=patrol_count,
            coverage_radius_km=coverage_radius_km,
            total_demand_points=total_points,
            total_weighted_risk=round(total_weight, 4),
            covered_demand_points=covered_points_count,
            covered_weighted_risk=round(covered_risk_val, 4),
            coverage_percentage=round(cov_pct, 2),
            uncovered_high_risk_points=uncovered_high_risk,
            selected_prps=selected_prps,
        )


prp_optimizer = PRPOptimizer()
