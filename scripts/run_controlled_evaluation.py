"""SafeZone Final Controlled Evaluation Script.

Executes controlled, reproducible academic benchmarks on the frozen SafeZone dataset:
1. K Sensitivity: K in {4, 6, 8, 10} at Radius = 3.0 km, Shift = ALL
2. Radius Sensitivity: Radius in {3.0, 4.0, 5.0 km} at K = 8, Shift = ALL
3. Shift-Specific Dynamic Analysis: Shifts in {ALL, MORNING, AFTERNOON, EVENING, NIGHT} at K = 8, Radius = 3.0 km
4. Primary Configuration Comparison: K = 8, Radius = 3.0 km, Shift = ALL

Validates all results, writes structured JSON, and generates publication-quality academic charts.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
import matplotlib.pyplot as plt

# Ensure backend is in pythonpath
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database.session import AsyncSessionLocal
from app.services.analytics_service import analytics_service
from app.schemas.analytics import EvaluationRequest


def validate_metric(strategy_name: str, m: dict, k: int, radius: float):
    """Validate numerical and logical bounds for an evaluation metric."""
    cov_pct = m["coverage_percentage"]
    w_cov_pct = m["weighted_risk_coverage_pct"]
    hr_cov_pct = m["high_risk_coverage_pct"]
    cov_pts = m["covered_demand_points"]
    tot_pts = m["total_demand_points"]
    cov_w = m["covered_weighted_risk"]
    tot_w = m["total_weighted_risk"]
    hr_cov = m["high_risk_covered"]
    hr_tot = m["high_risk_total"]
    mean_d = m["mean_distance_km"]
    max_d = m["max_distance_km"]
    p_cnt = m["patrol_count"]

    assert 0.0 <= cov_pct <= 100.0, f"Invalid cov_pct: {cov_pct}"
    assert 0.0 <= w_cov_pct <= 100.0, f"Invalid w_cov_pct: {w_cov_pct}"
    assert 0.0 <= hr_cov_pct <= 100.0, f"Invalid hr_cov_pct: {hr_cov_pct}"
    assert 0 <= cov_pts <= tot_pts, f"Covered pts {cov_pts} > total {tot_pts}"
    assert 0.0 <= cov_w <= tot_w + 1e-3, f"Covered weight {cov_w} > total {tot_w}"
    assert 0 <= hr_cov <= hr_tot, f"High risk covered {hr_cov} > total {hr_tot}"
    assert p_cnt <= k, f"Selected PRPs {p_cnt} > K {k}"
    assert mean_d >= 0.0, f"Negative mean distance {mean_d}"
    assert max_d >= mean_d - 1e-4, f"Max distance {max_d} < mean distance {mean_d}"


async def run_all_evaluations():
    out_dir = os.path.join("data", "evaluation_results")
    os.makedirs(out_dir, exist_ok=True)

    results_data = {
        "metadata": {
            "evaluation_title": "SafeZone Final Controlled Evaluation",
            "dataset_name": "SafeZone Prototype Dataset (Chennai Municipal Wards 1-200)",
            "dataset_incident_count": 10000,
            "random_seed": 42,
            "distance_metric": "Geodesic Haversine Distance (WGS84 Sphere, R=6371km)",
            "high_risk_threshold": "Risk weight >= 2.0 (High/Critical Severity)",
            "evaluated_at": datetime.utcnow().isoformat(),
        },
        "k_sensitivity": {},
        "radius_sensitivity": {},
        "shift_analysis": {},
        "primary_comparison": {},
    }

    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("SAFEZONE CONTROLLED EXPERIMENTAL EVALUATION")
        print("=" * 80)

        # -------------------------------------------------------------
        # 1. K SENSITIVITY EXPERIMENT (K in 4, 6, 8, 10; Radius=3.0 km; Shift=ALL)
        # -------------------------------------------------------------
        print("\n--- 1. Executing K Sensitivity Experiment (Radius=3.0 km, Shift=ALL) ---")
        k_values = [4, 6, 8, 10]
        for k in k_values:
            print(f"  Evaluating K = {k}...")
            req = EvaluationRequest(
                patrol_count=k,
                coverage_radius_km=3.0,
                time_period="ALL",
                use_stored_prps_if_available=False,
            )
            res = await analytics_service.evaluate_strategies(db, req)
            res_dict = json.loads(res.model_dump_json())

            validate_metric("REFERENCE", res_dict["reference"], k, 3.0)
            validate_metric("DYNAMIC", res_dict["dynamic"], k, 3.0)
            validate_metric("RANDOM", res_dict["random_baseline"], k, 3.0)

            results_data["k_sensitivity"][str(k)] = res_dict

        # -------------------------------------------------------------
        # 2. RADIUS SENSITIVITY EXPERIMENT (Radius in 3.0, 4.0, 5.0 km; K=8; Shift=ALL)
        # -------------------------------------------------------------
        print("\n--- 2. Executing Radius Sensitivity Experiment (K=8, Shift=ALL) ---")
        radius_values = [3.0, 4.0, 5.0]
        for r in radius_values:
            print(f"  Evaluating Radius = {r} km...")
            req = EvaluationRequest(
                patrol_count=8,
                coverage_radius_km=r,
                time_period="ALL",
                use_stored_prps_if_available=False,
            )
            res = await analytics_service.evaluate_strategies(db, req)
            res_dict = json.loads(res.model_dump_json())

            validate_metric("REFERENCE", res_dict["reference"], 8, r)
            validate_metric("DYNAMIC", res_dict["dynamic"], 8, r)
            validate_metric("RANDOM", res_dict["random_baseline"], 8, r)

            results_data["radius_sensitivity"][str(r)] = res_dict

        # -------------------------------------------------------------
        # 3. SHIFT-SPECIFIC DYNAMIC ANALYSIS (Shifts in ALL, MORNING, AFTERNOON, EVENING, NIGHT; K=8; Radius=3.0 km)
        # -------------------------------------------------------------
        print("\n--- 3. Executing Shift-Specific Dynamic Analysis (K=8, Radius=3.0 km) ---")
        shifts = ["ALL", "MORNING", "AFTERNOON", "EVENING", "NIGHT"]
        for s in shifts:
            print(f"  Evaluating Shift = {s}...")
            req = EvaluationRequest(
                patrol_count=8,
                coverage_radius_km=3.0,
                time_period=s,
                use_stored_prps_if_available=False,
            )
            res = await analytics_service.evaluate_strategies(db, req)
            res_dict = json.loads(res.model_dump_json())

            validate_metric("DYNAMIC", res_dict["dynamic"], 8, 3.0)
            results_data["shift_analysis"][s] = res_dict["dynamic"]

        # Primary Configuration: K=8, Radius=3.0 km, Shift=ALL
        results_data["primary_comparison"] = results_data["k_sensitivity"]["8"]

    # -------------------------------------------------------------
    # 4. WRITE JSON ARTIFACT
    # -------------------------------------------------------------
    json_path = os.path.join(out_dir, "safezone_evaluation_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)
    print(f"\n[Artifact Saved] Machine-readable results written to: {json_path}")

    # -------------------------------------------------------------
    # 5. GENERATE PUBLICATION-QUALITY CHARTS
    # -------------------------------------------------------------
    print("\n--- Generating Academic Evaluation Charts ---")
    plt.rcParams.update({
        "font.sans-serif": "DejaVu Sans",
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "legend.fontsize": 10,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "figure.titlesize": 14,
        "axes.grid": True,
        "grid.alpha": 0.35,
        "grid.linestyle": "--",
    })

    colors = {
        "Reference": "#2563eb",  # Blue
        "Dynamic": "#7c3aed",    # Purple
        "Random": "#94a3b8",     # Slate Gray
    }

    # Chart 1: K vs Spatial Coverage %
    plt.figure(figsize=(7, 4.5))
    for strat, col, marker in [("reference", colors["Reference"], "o"), ("dynamic", colors["Dynamic"], "s"), ("random_baseline", colors["Random"], "^")]:
        y = [results_data["k_sensitivity"][str(k)][strat]["coverage_percentage"] for k in k_values]
        label = "Reference PRPs" if strat == "reference" else "Dynamic PRPs" if strat == "dynamic" else "Random Baseline (Seed=42)"
        plt.plot(k_values, y, marker=marker, color=col, linewidth=2, markersize=7, label=label)
    plt.title("Spatial Incident Coverage vs. Deployment Capacity (K)")
    plt.xlabel("PRP Deployment Capacity (K)")
    plt.ylabel("Spatial Coverage (%)")
    plt.xticks(k_values)
    plt.ylim(30, 90)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart1_path = os.path.join(out_dir, "k_vs_spatial_coverage.png")
    plt.savefig(chart1_path, dpi=300)
    plt.close()
    print(f"  Chart 1: {chart1_path}")

    # Chart 2: K vs Weighted Risk Coverage %
    plt.figure(figsize=(7, 4.5))
    for strat, col, marker in [("reference", colors["Reference"], "o"), ("dynamic", colors["Dynamic"], "s"), ("random_baseline", colors["Random"], "^")]:
        y = [results_data["k_sensitivity"][str(k)][strat]["weighted_risk_coverage_pct"] for k in k_values]
        label = "Reference PRPs" if strat == "reference" else "Dynamic PRPs" if strat == "dynamic" else "Random Baseline (Seed=42)"
        plt.plot(k_values, y, marker=marker, color=col, linewidth=2, markersize=7, label=label)
    plt.title("Weighted Risk Coverage vs. Deployment Capacity (K)")
    plt.xlabel("PRP Deployment Capacity (K)")
    plt.ylabel("Weighted Risk Coverage (%)")
    plt.xticks(k_values)
    plt.ylim(35, 95)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart2_path = os.path.join(out_dir, "k_vs_weighted_risk_coverage.png")
    plt.savefig(chart2_path, dpi=300)
    plt.close()
    print(f"  Chart 2: {chart2_path}")

    # Chart 3: K vs High-Risk Coverage %
    plt.figure(figsize=(7, 4.5))
    for strat, col, marker in [("reference", colors["Reference"], "o"), ("dynamic", colors["Dynamic"], "s"), ("random_baseline", colors["Random"], "^")]:
        y = [results_data["k_sensitivity"][str(k)][strat]["high_risk_coverage_pct"] for k in k_values]
        label = "Reference PRPs" if strat == "reference" else "Dynamic PRPs" if strat == "dynamic" else "Random Baseline (Seed=42)"
        plt.plot(k_values, y, marker=marker, color=col, linewidth=2, markersize=7, label=label)
    plt.title("High-Risk Incident Coverage vs. Deployment Capacity (K)")
    plt.xlabel("PRP Deployment Capacity (K)")
    plt.ylabel("High-Risk Coverage (%)")
    plt.xticks(k_values)
    plt.ylim(30, 95)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart3_path = os.path.join(out_dir, "k_vs_high_risk_coverage.png")
    plt.savefig(chart3_path, dpi=300)
    plt.close()
    print(f"  Chart 3: {chart3_path}")

    # Chart 4: Radius vs Spatial Coverage %
    plt.figure(figsize=(7, 4.5))
    for strat, col, marker in [("reference", colors["Reference"], "o"), ("dynamic", colors["Dynamic"], "s"), ("random_baseline", colors["Random"], "^")]:
        y = [results_data["radius_sensitivity"][str(r)][strat]["coverage_percentage"] for r in radius_values]
        label = "Reference PRPs" if strat == "reference" else "Dynamic PRPs" if strat == "dynamic" else "Random Baseline (Seed=42)"
        plt.plot(radius_values, y, marker=marker, color=col, linewidth=2, markersize=7, label=label)
    plt.title("Spatial Incident Coverage vs. Service Radius (K = 8)")
    plt.xlabel("Coverage Radius (km)")
    plt.ylabel("Spatial Coverage (%)")
    plt.xticks(radius_values)
    plt.ylim(40, 100)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart4_path = os.path.join(out_dir, "radius_vs_spatial_coverage.png")
    plt.savefig(chart4_path, dpi=300)
    plt.close()
    print(f"  Chart 4: {chart4_path}")

    # Chart 5: Radius vs Weighted Risk Coverage %
    plt.figure(figsize=(7, 4.5))
    for strat, col, marker in [("reference", colors["Reference"], "o"), ("dynamic", colors["Dynamic"], "s"), ("random_baseline", colors["Random"], "^")]:
        y = [results_data["radius_sensitivity"][str(r)][strat]["weighted_risk_coverage_pct"] for r in radius_values]
        label = "Reference PRPs" if strat == "reference" else "Dynamic PRPs" if strat == "dynamic" else "Random Baseline (Seed=42)"
        plt.plot(radius_values, y, marker=marker, color=col, linewidth=2, markersize=7, label=label)
    plt.title("Weighted Risk Coverage vs. Service Radius (K = 8)")
    plt.xlabel("Coverage Radius (km)")
    plt.ylabel("Weighted Risk Coverage (%)")
    plt.xticks(radius_values)
    plt.ylim(50, 100)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart5_path = os.path.join(out_dir, "radius_vs_weighted_risk_coverage.png")
    plt.savefig(chart5_path, dpi=300)
    plt.close()
    print(f"  Chart 5: {chart5_path}")

    # Chart 6: Strategy vs Mean Geodesic Distance (K=8, Radius=3.0 km, Shift=ALL)
    plt.figure(figsize=(6.5, 4.5))
    primary = results_data["primary_comparison"]
    strats = ["Reference PRPs", "Dynamic PRPs", "Random Baseline"]
    mean_distances = [
        primary["reference"]["mean_distance_km"],
        primary["dynamic"]["mean_distance_km"],
        primary["random_baseline"]["mean_distance_km"],
    ]
    bar_colors = [colors["Reference"], colors["Dynamic"], colors["Random"]]
    bars = plt.bar(strats, mean_distances, color=bar_colors, width=0.5, edgecolor="#334155", linewidth=1.2)
    plt.title("Mean Geodesic Distance to Nearest PRP (K = 8, Radius = 3.0 km)")
    plt.ylabel("Mean Geodesic Distance (km)")
    plt.ylim(0, 5.5)
    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2., h + 0.1, f"{h:.3f} km", ha="center", va="bottom", fontweight="bold", fontsize=10)
    plt.tight_layout()
    chart6_path = os.path.join(out_dir, "strategy_vs_mean_distance.png")
    plt.savefig(chart6_path, dpi=300)
    plt.close()
    print(f"  Chart 6: {chart6_path}")

    # Chart 7: Shift vs Weighted Risk Coverage % (Dynamic Strategy, K=8, Radius=3.0 km)
    plt.figure(figsize=(7, 4.5))
    shift_labels = ["ALL", "MORNING", "AFTERNOON", "EVENING", "NIGHT"]
    shift_w_cov = [results_data["shift_analysis"][s]["weighted_risk_coverage_pct"] for s in shift_labels]
    shift_sp_cov = [results_data["shift_analysis"][s]["coverage_percentage"] for s in shift_labels]
    
    x = list(range(len(shift_labels)))
    w = 0.35
    plt.bar([i - w/2 for i in x], shift_w_cov, width=w, color="#7c3aed", label="Weighted Risk Coverage %", edgecolor="#334155", linewidth=1)
    plt.bar([i + w/2 for i in x], shift_sp_cov, width=w, color="#38bdf8", label="Spatial Coverage %", edgecolor="#334155", linewidth=1)
    plt.title("Dynamic PRP Performance by Operational Shift (K = 8, Radius = 3.0 km)")
    plt.xlabel("Operational Shift")
    plt.ylabel("Coverage (%)")
    plt.xticks(x, shift_labels)
    plt.ylim(50, 90)
    plt.legend(loc="lower right")
    plt.tight_layout()
    chart7_path = os.path.join(out_dir, "shift_vs_weighted_risk_coverage.png")
    plt.savefig(chart7_path, dpi=300)
    plt.close()
    print(f"  Chart 7: {chart7_path}")

    print("\nAll controlled evaluations completed successfully!")
    return results_data


if __name__ == "__main__":
    asyncio.run(run_all_evaluations())
