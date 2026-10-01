import React, { useState, useEffect } from 'react';
import {
  Compass,
  Play,
  Save,
  CheckCircle,
  Percent,
  MapPin,
  Clock,
  Layers,
  AlertTriangle,
  UserCheck,
  RefreshCw,
} from 'lucide-react';
import { prpApi, patrolsApi } from '../services/api';
import LeafletMap from '../components/LeafletMap';

export default function PRPOptimizationPage({ setActiveTab }) {
  // Optimization Form
  const [mode, setMode] = useState('DYNAMIC');
  const [shift, setShift] = useState('ALL');
  const [patrolCount, setPatrolCount] = useState(10);
  const [coverageRadiusKm, setCoverageRadiusKm] = useState(3.0);

  // Results State
  const [optResult, setOptResult] = useState(null);
  const [optimizing, setOptimizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [assigning, setAssigning] = useState(false);

  // Initial load
  useEffect(() => {
    handleRunOptimization(false);
  }, []);

  const handleRunOptimization = async (saveRun = false) => {
    if (saveRun) setSaving(true);
    else setOptimizing(true);

    try {
      const payload = {
        mode,
        time_period: shift,
        patrol_count: parseInt(patrolCount),
        coverage_radius_km: parseFloat(coverageRadiusKm),
        save_run: saveRun,
      };

      const res = saveRun
        ? await prpApi.createRun(payload)
        : await prpApi.optimize(payload);

      setOptResult(res);
    } catch (err) {
      alert(err.response?.data?.detail || 'Optimization solver failed');
    } finally {
      setOptimizing(false);
      setSaving(false);
    }
  };

  const handleUpdateStatus = async (prpId, newStatus) => {
    try {
      await prpApi.updateStatus(prpId, newStatus);
      if (optResult?.selected_prps) {
        setOptResult((prev) => ({
          ...prev,
          selected_prps: prev.selected_prps.map((p) =>
            p.id === prpId ? { ...p, status: newStatus } : p
          ),
        }));
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update PRP status');
    }
  };

  const handleAutoAssign = async () => {
    setAssigning(true);
    try {
      const res = await patrolsApi.createAutoAssignment({
        optimization_run_id: optResult?.run_id || undefined,
        shift_start: new Date().toISOString(),
      });
      alert(`Auto-Assignment Complete: Assigned ${res.assigned_count} patrol units to active PRPs.`);
      if (setActiveTab) setActiveTab('patrols');
    } catch (err) {
      alert(err.response?.data?.detail || 'Auto-assignment failed');
    } finally {
      setAssigning(false);
    }
  };

  return (
    <div className="page-container">
      {/* Top Configuration & Trigger Card */}
      <div className="dashboard-card" style={{ marginBottom: '20px' }}>
        <div className="card-header">
          <div>
            <h3 className="card-title">Google OR-Tools Maximum Crime-Risk Coverage Optimizer</h3>
            <p className="card-subtitle">Formulates and solves mixed-integer linear program (MCLP) preventing duplicate coverage</p>
          </div>
        </div>

        <div className="card-body">
          <div className="opt-controls-grid">
            <div className="form-group">
              <label>Optimization Mode *</label>
              <select className="form-control" value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="DYNAMIC">DYNAMIC (Real-Time Recency & Shift Decay)</option>
                <option value="REFERENCE">REFERENCE (Historical Baseline Patterns)</option>
              </select>
            </div>

            <div className="form-group">
              <label>Target Patrol Shift *</label>
              <select className="form-control" value={shift} onChange={(e) => setShift(e.target.value)}>
                <option value="ALL">ALL SHIFTS (24 Hours)</option>
                <option value="MORNING">MORNING (06:00 - 12:00)</option>
                <option value="AFTERNOON">AFTERNOON (12:00 - 18:00)</option>
                <option value="EVENING">EVENING (18:00 - 22:00)</option>
                <option value="NIGHT">NIGHT (22:00 - 06:00)</option>
              </select>
            </div>

            <div className="form-group">
              <label>PRP Deployment Capacity (K)</label>
              <input
                type="number"
                min="1"
                max="50"
                className="form-control"
                value={patrolCount}
                onChange={(e) => setPatrolCount(e.target.value)}
              />
              <span style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '2px', display: 'block' }}>
                Maximum number of PRPs the optimizer may select.
              </span>
            </div>

            <div className="form-group">
              <label>Coverage Radius (km)</label>
              <select
                className="form-control"
                value={coverageRadiusKm}
                onChange={(e) => setCoverageRadiusKm(e.target.value)}
              >
                <option value="3.0">3.0 km (Standard Urban Buffer)</option>
                <option value="4.0">4.0 km (Suburban Extended)</option>
                <option value="5.0">5.0 km (Maximum Radius)</option>
              </select>
            </div>
          </div>

          <div className="opt-actions-row">
            <button
              className="btn btn-primary"
              onClick={() => handleRunOptimization(false)}
              disabled={optimizing || saving}
            >
              <Play size={16} />
              <span>{optimizing ? 'Solving with OR-Tools...' : 'Generate Optimization Preview'}</span>
            </button>

            <button
              className="btn btn-success"
              onClick={() => handleRunOptimization(true)}
              disabled={optimizing || saving}
            >
              <Save size={16} />
              <span>{saving ? 'Persisting Run...' : 'Approve & Save Run to Database'}</span>
            </button>

            {optResult?.selected_prps?.length > 0 && (
              <button
                className="btn btn-secondary"
                onClick={handleAutoAssign}
                disabled={assigning}
              >
                <UserCheck size={16} />
                <span>{assigning ? 'Assigning Units...' : 'Auto-Assign Available Patrol Units'}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Solver Metrics Summary Cards */}
      {optResult && (
        <div className="kpi-grid" style={{ marginBottom: '20px' }}>
          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">UNIQUE RISK COVERAGE</span>
              <Percent size={18} color="#7c3aed" />
            </div>
            <div className="kpi-value">{optResult.coverage_percentage}%</div>
            <div className="kpi-footer">
              <span className="kpi-tag kpi-tag-success">{optResult.covered_weighted_risk} / {optResult.total_weighted_risk} Risk</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">SELECTED PRPs</span>
              <Compass size={18} color="#2563eb" />
            </div>
            <div className="kpi-value">{optResult.selected_prps?.length || 0}</div>
            <div className="kpi-footer">
              <span className="kpi-tag kpi-tag-info">Target Capacity: {optResult.available_patrol_count}</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">SOLVER STATUS</span>
              <CheckCircle size={18} color="#16a34a" />
            </div>
            <div className="kpi-value" style={{ fontSize: '1.4rem' }}>{optResult.status}</div>
            <div className="kpi-footer">
              <span className="kpi-tag kpi-tag-success">{optResult.execution_time_seconds}s execution</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">UNCOVERED HIGH RISK</span>
              <AlertTriangle size={18} color="#ea580c" />
            </div>
            <div className="kpi-value">{optResult.uncovered_high_risk_points}</div>
            <div className="kpi-footer">
              <span className="kpi-tag kpi-tag-warning">Demand Points Outside Radius</span>
            </div>
          </div>
        </div>
      )}

      {/* Map & Ranked PRPs 2-Column Section */}
      <div className="dashboard-grid">
        {/* Left: Map Preview with Coverage Rings */}
        <div className="dashboard-card" style={{ height: '480px', padding: 0, overflow: 'hidden' }}>
          <LeafletMap
            prps={optResult?.selected_prps || []}
            showPRPs={true}
            showCrimes={false}
            coverageRadiusKm={parseFloat(coverageRadiusKm)}
            height="100%"
          />
        </div>

        {/* Right: Ranked PRPs Table */}
        <div className="dashboard-card" style={{ height: '480px', display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <h3 className="card-title">Prioritized Patrol Response Points (PRPs)</h3>
            <span className="badge badge-light">{optResult?.selected_prps?.length || 0} Recommended</span>
          </div>

          <div className="card-body" style={{ flex: 1, overflowY: 'auto', padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>RANK</th>
                  <th>WARD & ZONE</th>
                  <th>MARGINAL RISK</th>
                  <th>STATUS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {!optResult?.selected_prps || optResult.selected_prps.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{ textAlign: 'center', padding: '24px', color: '#94a3b8' }}>
                      Click "Generate Optimization Preview" to solve.
                    </td>
                  </tr>
                ) : (
                  optResult.selected_prps.map((p) => (
                    <tr key={p.rank}>
                      <td>
                        <span className="code-badge" style={{ backgroundColor: '#eff6ff', color: '#2563eb' }}>
                          #{p.rank}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontSize: '12px' }}>
                          <strong>Ward {p.ward_no}</strong>
                          <div style={{ color: '#64748b' }}>{p.zone_name}</div>
                        </div>
                      </td>
                      <td>
                        <span className="kpi-tag kpi-tag-info" style={{ fontWeight: 600 }}>
                          {(p.risk_score || 0).toFixed(2)}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${p.status === 'ACTIVE' ? 'success' : p.status === 'APPROVED' ? 'primary' : 'warning'}`}>
                          {p.status || 'RECOMMENDED'}
                        </span>
                      </td>
                      <td>
                        <div className="action-buttons-group">
                          {p.id && p.status !== 'APPROVED' && (
                            <button
                              className="btn btn-secondary btn-xs"
                              onClick={() => handleUpdateStatus(p.id, 'APPROVED')}
                            >
                              Approve
                            </button>
                          )}
                          {p.id && p.status !== 'ACTIVE' && (
                            <button
                              className="btn btn-success btn-xs"
                              onClick={() => handleUpdateStatus(p.id, 'ACTIVE')}
                            >
                              Activate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
