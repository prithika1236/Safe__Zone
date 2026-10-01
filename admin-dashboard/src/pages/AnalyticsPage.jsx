import React, { useState, useEffect } from 'react';
import {
  BarChart3,
  TrendingUp,
  Shield,
  Layers,
  CheckCircle2,
  Target,
  Clock,
  AlertTriangle,
  RefreshCw,
  Info,
  Car,
  FileText,
  Activity,
  Percent,
  X,
} from 'lucide-react';
import { analyticsApi } from '../services/api';

export default function AnalyticsPage() {
  const [evaluation, setEvaluation] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState(null);

  // Evaluation Parameters
  const [patrolCount, setPatrolCount] = useState(8);
  const [coverageRadiusKm, setCoverageRadiusKm] = useState(3.0);
  const [timePeriod, setTimePeriod] = useState('ALL');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch live operational summary
      try {
        const sumRes = await analyticsApi.getSummary();
        setSummary(sumRes);
      } catch (sumErr) {
        console.error('Failed to load operational summary:', sumErr);
      }

      // 2. Fetch strategy evaluation
      try {
        const evalRes = await analyticsApi.evaluate({
          patrol_count: Number(patrolCount),
          coverage_radius_km: Number(coverageRadiusKm),
          time_period: timePeriod,
          use_stored_prps_if_available: true,
        });
        setEvaluation(evalRes);
      } catch (evalErr) {
        console.error('Failed to run strategy evaluation:', evalErr);
        setError(evalErr.response?.data?.detail || 'Strategy evaluation calculation failed. Please verify solver configuration.');
      }
    } catch (err) {
      console.error('Analytics data fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEvaluation = async (e) => {
    e.preventDefault();
    setEvaluating(true);
    setError(null);
    try {
      const evalRes = await analyticsApi.evaluate({
        patrol_count: Number(patrolCount),
        coverage_radius_km: Number(coverageRadiusKm),
        time_period: timePeriod,
        use_stored_prps_if_available: false, // Explicit re-evaluation
      });
      setEvaluation(evalRes);
    } catch (err) {
      console.error('Evaluation run failed:', err);
      setError(err.response?.data?.detail || 'Strategy evaluation calculation failed. Please verify solver configuration.');
    } finally {
      setEvaluating(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const ref = evaluation?.reference;
  const dyn = evaluation?.dynamic;
  const rnd = evaluation?.random_baseline;

  return (
    <div className="page-container">
      {/* Top Toolbar */}
      <div className="toolbar-card">
        <div className="filters-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart3 size={18} color="#2563eb" />
            <strong style={{ fontSize: '0.95rem' }}>Academic Strategy Evaluation & Analytics</strong>
          </div>
        </div>

        <div className="actions-row">
          <button className="btn btn-secondary btn-sm" onClick={fetchData} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh Metrics</span>
          </button>
        </div>
      </div>

      {/* Dataset & Prototype Transparency Banner */}
      <div className="alert-banner alert-info" style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <Info size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <div style={{ fontWeight: 700, marginBottom: '2px' }}>
            Academic Prototype Evaluation Dataset — {evaluation?.data_source || 'Chennai Municipal Wards 1–200'}
          </div>
          <p style={{ fontSize: '12px', opacity: 0.9 }}>
            All metrics are computed in real time from actual SafeZone demand data and optimization results. Geodesic (Haversine) separation is used for spatial distance indicators. Response times are not artificially fabricated without verified road routing telemetry.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-danger">
          <AlertTriangle size={18} />
          <div style={{ flex: 1 }}>{error}</div>
          <button className="modal-close" onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      {/* Interactive Evaluation Parameter Controls */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Solver Simulation Parameters</h3>
            <p className="card-subtitle">Tune patrol capacity K, spatial buffer radius, and shift window</p>
          </div>
        </div>

        <div className="card-body">
          <form onSubmit={handleRunEvaluation} className="filters-row" style={{ alignItems: 'flex-end', gap: '14px' }}>
            <div className="form-group">
              <label>Patrol Budget (PRP Count K)</label>
              <input
                type="number"
                min="1"
                max="50"
                className="form-control"
                value={patrolCount}
                onChange={(e) => setPatrolCount(e.target.value)}
                style={{ width: '130px' }}
              />
            </div>

            <div className="form-group">
              <label>Coverage Radius (km)</label>
              <input
                type="number"
                step="0.5"
                min="0.5"
                max="15.0"
                className="form-control"
                value={coverageRadiusKm}
                onChange={(e) => setCoverageRadiusKm(e.target.value)}
                style={{ width: '130px' }}
              />
            </div>

            <div className="form-group">
              <label>Shift / Time Period</label>
              <select
                className="form-control"
                value={timePeriod}
                onChange={(e) => setTimePeriod(e.target.value)}
              >
                <option value="ALL">ALL Shifts (24 Hours)</option>
                <option value="MORNING">Morning (06:00 - 12:00)</option>
                <option value="AFTERNOON">Afternoon (12:00 - 18:00)</option>
                <option value="EVENING">Evening (18:00 - 22:00)</option>
                <option value="NIGHT">Night (22:00 - 06:00)</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={evaluating || loading}
              className="btn btn-primary"
            >
              {evaluating ? (
                <>
                  <RefreshCw size={14} className="spin" />
                  <span>Evaluating...</span>
                </>
              ) : (
                <>
                  <Target size={14} />
                  <span>Run Comparative Evaluation</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* STRATEGY COMPARISON CARDS */}
      {evaluation && (
        <div className="three-col-grid">
          {/* Reference PRPs */}
          <div className="comparison-card">
            <div className="comparison-header">
              <span className="comparison-title">Reference PRPs</span>
              <span className="badge badge-secondary">Historical Baseline</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Weighted Risk Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#334155' }}>{ref?.weighted_risk_coverage_pct}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Demand Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#334155' }}>{ref?.coverage_percentage}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>High-Risk Cov.</span>
                <span style={{ fontWeight: 700 }}>{ref?.high_risk_coverage_pct}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Mean Distance</span>
                <span style={{ fontWeight: 700 }}>{ref?.mean_distance_km} km</span>
              </div>
            </div>
          </div>

          {/* Dynamic SafeZone PRPs */}
          <div className="comparison-card" style={{ borderColor: '#3b82f6', background: '#f8fafc', boxShadow: '0 0 0 1px #3b82f6' }}>
            <div className="comparison-header">
              <span className="comparison-title" style={{ color: '#1d4ed8' }}>Dynamic SafeZone</span>
              <span className="badge badge-primary">Time-Decayed MCLP</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Weighted Risk Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#2563eb' }}>{dyn?.weighted_risk_coverage_pct}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Demand Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#2563eb' }}>{dyn?.coverage_percentage}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>High-Risk Cov.</span>
                <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{dyn?.high_risk_coverage_pct}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Mean Distance</span>
                <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{dyn?.mean_distance_km} km</span>
              </div>
            </div>
          </div>

          {/* Random Baseline */}
          <div className="comparison-card">
            <div className="comparison-header">
              <span className="comparison-title" style={{ color: '#64748b' }}>Random Baseline</span>
              <span className="badge badge-secondary">Seed=42</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Weighted Risk Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#64748b' }}>{rnd?.weighted_risk_coverage_pct || 0}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Demand Cov.</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#64748b' }}>{rnd?.coverage_percentage || 0}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>High-Risk Cov.</span>
                <span style={{ fontWeight: 700, color: '#64748b' }}>{rnd?.high_risk_coverage_pct || 0}%</span>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Mean Distance</span>
                <span style={{ fontWeight: 700, color: '#64748b' }}>{rnd?.mean_distance_km || 0} km</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STRATEGY COMPARISON TABLE */}
      {evaluation && (
        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Comprehensive Strategy Evaluation Breakdown</h3>
              <p className="card-subtitle">
                Evaluated on {evaluation.dataset_incident_count} Incidents • Radius {evaluation.coverage_radius_km} km • K={evaluation.patrol_count}
              </p>
            </div>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>EVALUATION METRIC</th>
                  <th style={{ textAlign: 'center' }}>REFERENCE PRPs</th>
                  <th style={{ textAlign: 'center', backgroundColor: '#eff6ff', color: '#1d4ed8' }}>DYNAMIC SAFEZONE</th>
                  <th style={{ textAlign: 'center' }}>RANDOM BASELINE*</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Allocated Patrol Count (K)</strong></td>
                  <td style={{ textAlign: 'center' }}>{ref?.patrol_count}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.patrol_count}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.patrol_count || '-'}</td>
                </tr>
                <tr>
                  <td>Total Demand / Risk Points</td>
                  <td style={{ textAlign: 'center' }}>{ref?.total_demand_points}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.total_demand_points}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.total_demand_points || '-'}</td>
                </tr>
                <tr>
                  <td>Covered Demand Points</td>
                  <td style={{ textAlign: 'center' }}>{ref?.covered_demand_points}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.covered_demand_points}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.covered_demand_points || '-'}</td>
                </tr>
                <tr style={{ backgroundColor: '#f8fafc' }}>
                  <td><strong>Spatial Demand Coverage Percentage</strong></td>
                  <td style={{ textAlign: 'center', fontWeight: 700 }}>{ref?.coverage_percentage}%</td>
                  <td style={{ textAlign: 'center', fontWeight: 800, color: '#2563eb', backgroundColor: '#eff6ff' }}>{dyn?.coverage_percentage}%</td>
                  <td style={{ textAlign: 'center' }}>{rnd?.coverage_percentage || 0}%</td>
                </tr>
                <tr>
                  <td>Total Weighted Risk</td>
                  <td style={{ textAlign: 'center' }}>{ref?.total_weighted_risk}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.total_weighted_risk}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.total_weighted_risk || '-'}</td>
                </tr>
                <tr>
                  <td>Covered Weighted Risk (Zero Double-Count)</td>
                  <td style={{ textAlign: 'center' }}>{ref?.covered_weighted_risk}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.covered_weighted_risk}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.covered_weighted_risk || '-'}</td>
                </tr>
                <tr style={{ backgroundColor: '#eff6ff' }}>
                  <td><strong style={{ color: '#1d4ed8' }}>Weighted Risk Coverage Percentage</strong></td>
                  <td style={{ textAlign: 'center', fontWeight: 700 }}>{ref?.weighted_risk_coverage_pct}%</td>
                  <td style={{ textAlign: 'center', fontWeight: 900, color: '#2563eb', fontSize: '1rem', backgroundColor: '#dbeafe' }}>{dyn?.weighted_risk_coverage_pct}%</td>
                  <td style={{ textAlign: 'center' }}>{rnd?.weighted_risk_coverage_pct || 0}%</td>
                </tr>
                <tr>
                  <td>High-Risk Points Total (Weight ≥ 2.0)</td>
                  <td style={{ textAlign: 'center' }}>{ref?.high_risk_total}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.high_risk_total}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.high_risk_total || '-'}</td>
                </tr>
                <tr>
                  <td>High-Risk Points Covered</td>
                  <td style={{ textAlign: 'center' }}>{ref?.high_risk_covered}</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.high_risk_covered}</td>
                  <td style={{ textAlign: 'center', color: '#94a3b8' }}>{rnd?.high_risk_covered || '-'}</td>
                </tr>
                <tr style={{ backgroundColor: '#f8fafc' }}>
                  <td><strong>High-Risk Coverage Percentage</strong></td>
                  <td style={{ textAlign: 'center', fontWeight: 700 }}>{ref?.high_risk_coverage_pct}%</td>
                  <td style={{ textAlign: 'center', fontWeight: 800, color: '#2563eb', backgroundColor: '#eff6ff' }}>{dyn?.high_risk_coverage_pct}%</td>
                  <td style={{ textAlign: 'center' }}>{rnd?.high_risk_coverage_pct || 0}%</td>
                </tr>
                <tr>
                  <td>Mean Geodesic Distance to Nearest PRP</td>
                  <td style={{ textAlign: 'center' }}>{ref?.mean_distance_km} km</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.mean_distance_km} km</td>
                  <td style={{ textAlign: 'center' }}>{rnd?.mean_distance_km || 0} km</td>
                </tr>
                <tr>
                  <td>Maximum Geodesic Distance to Nearest PRP</td>
                  <td style={{ textAlign: 'center' }}>{ref?.max_distance_km} km</td>
                  <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb', backgroundColor: '#f8fafc' }}>{dyn?.max_distance_km} km</td>
                  <td style={{ textAlign: 'center' }}>{rnd?.max_distance_km || 0} km</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="card-footer">
            <span style={{ fontSize: '11px', color: '#64748b' }}>
              * Random Baseline uses deterministic candidate sampling with seed=42 across identical candidate space.
            </span>
          </div>
        </div>
      )}

      {/* VISUAL PROGRESS BARS COMPARISON */}
      {evaluation && (
        <div className="two-col-grid">
          {/* Chart 1: Weighted Risk Coverage Comparison */}
          <div className="dashboard-card">
            <div className="card-header">
              <h4 className="card-title">Weighted Risk Coverage (%)</h4>
              <span className="badge badge-light">Zero Double-Count</span>
            </div>
            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <strong style={{ color: '#2563eb' }}>Dynamic SafeZone</strong>
                  <strong style={{ color: '#2563eb' }}>{dyn?.weighted_risk_coverage_pct}%</strong>
                </div>
                <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, dyn?.weighted_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#2563eb', borderRadius: '9999px' }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span>Reference Historical</span>
                  <span style={{ fontWeight: 600 }}>{ref?.weighted_risk_coverage_pct}%</span>
                </div>
                <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, ref?.weighted_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#64748b', borderRadius: '9999px' }} />
                </div>
              </div>

              {rnd && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: '#94a3b8' }}>Random Baseline</span>
                    <span style={{ color: '#94a3b8', fontWeight: 600 }}>{rnd?.weighted_risk_coverage_pct}%</span>
                  </div>
                  <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, rnd?.weighted_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#cbd5e1', borderRadius: '9999px' }} />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Chart 2: High-Risk Points Coverage Comparison */}
          <div className="dashboard-card">
            <div className="card-header">
              <h4 className="card-title">High-Risk Points Coverage (%)</h4>
              <span className="badge badge-light">Weight ≥ 2.0</span>
            </div>
            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <strong style={{ color: '#7c3aed' }}>Dynamic SafeZone</strong>
                  <strong style={{ color: '#7c3aed' }}>{dyn?.high_risk_coverage_pct}%</strong>
                </div>
                <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, dyn?.high_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#7c3aed', borderRadius: '9999px' }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span>Reference Historical</span>
                  <span style={{ fontWeight: 600 }}>{ref?.high_risk_coverage_pct}%</span>
                </div>
                <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(100, ref?.high_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#64748b', borderRadius: '9999px' }} />
                </div>
              </div>

              {rnd && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: '#94a3b8' }}>Random Baseline</span>
                    <span style={{ color: '#94a3b8', fontWeight: 600 }}>{rnd?.high_risk_coverage_pct}%</span>
                  </div>
                  <div style={{ width: '100%', height: '10px', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, rnd?.high_risk_coverage_pct || 0)}%`, height: '100%', backgroundColor: '#cbd5e1', borderRadius: '9999px' }} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* OPERATIONAL SUMMARY SECTION */}
      {summary && (
        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Live Operational State & Fleet Summary</h3>
              <p className="card-subtitle">Real-time resource allocation and telemetry counts</p>
            </div>
          </div>

          <div className="card-body">
            <div className="kpi-grid">
              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">TOTAL CRIMES</span>
                  <FileText size={16} color="#64748b" />
                </div>
                <div className="kpi-value">{summary.total_crimes}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-info">Logged Records</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">PATROL FLEET</span>
                  <Car size={16} color="#2563eb" />
                </div>
                <div className="kpi-value">{summary.total_patrol_units}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-info">Registered Units</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">AVAILABLE UNITS</span>
                  <CheckCircle2 size={16} color="#10b981" />
                </div>
                <div className="kpi-value">{summary.available_patrols}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-success">Ready for Call</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">DISPATCHED</span>
                  <Activity size={16} color="#d97706" />
                </div>
                <div className="kpi-value">{summary.dispatched_patrols}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-warning">En Route / Scene</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">ACTIVE PRPs</span>
                  <Target size={16} color="#7c3aed" />
                </div>
                <div className="kpi-value">{summary.active_prps}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-success">Active Circles</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-header">
                  <span className="kpi-label">ACTIVE SOS</span>
                  <AlertTriangle size={16} color="#dc2626" />
                </div>
                <div className="kpi-value">{summary.active_sos_incidents}</div>
                <div className="kpi-footer">
                  <span className="kpi-tag kpi-tag-danger">Distress Alerts</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
