import React, { useState, useEffect } from 'react';
import { patrolsApi, policeApi, prpApi } from '../services/api';
import {
  Shield,
  Truck,
  Plus,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  MapPin,
  UserCheck,
  Zap,
  X,
} from 'lucide-react';

export default function PatrolsPage() {
  const [activeTab, setActiveTab] = useState('units'); // 'units' | 'assignments'
  const [units, setUnits] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [officers, setOfficers] = useState([]);
  const [activePRPs, setActivePRPs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Filters
  const [unitStatusFilter, setUnitStatusFilter] = useState('');
  const [assignStatusFilter, setAssignStatusFilter] = useState('');

  // Modals
  const [showCreateUnitModal, setShowCreateUnitModal] = useState(false);
  const [showManualAssignModal, setShowManualAssignModal] = useState(false);
  const [showAutoAssignModal, setShowAutoAssignModal] = useState(false);

  // Create Unit Form
  const [unitForm, setUnitForm] = useState({
    unit_code: '',
    call_sign: '',
    patrol_type: 'CAR',
    lead_officer_id: '',
    is_available: true,
  });

  // Manual Assign Form
  const [manualAssignForm, setManualAssignForm] = useState({
    patrol_unit_id: '',
    officer_id: '',
    prp_id: '',
    shift: 'NIGHT',
    notes: '',
  });

  // Auto Assign Form
  const [autoAssignForm, setAutoAssignForm] = useState({
    shift: 'NIGHT',
    max_radius_km: 15.0,
  });

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [unitsRes, assignRes, officersRes, prpsRes] = await Promise.all([
        policeApi.listUnits({ status: unitStatusFilter || undefined }),
        patrolsApi.listAssignments({ status: assignStatusFilter || undefined }),
        policeApi.listOfficers({ is_active: true }),
        prpApi.getActive().catch(() => ({ prps: [] })),
      ]);

      setUnits(unitsRes.items || unitsRes || []);
      setAssignments(assignRes.items || assignRes || []);
      setOfficers(officersRes.items || officersRes || []);
      setActivePRPs(prpsRes.prps || prpsRes.items || (Array.isArray(prpsRes) ? prpsRes : []));
    } catch (err) {
      console.error('Failed to load patrol data:', err);
      setError('Failed to load patrol data from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [unitStatusFilter, assignStatusFilter]);

  const handleCreateUnit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await policeApi.createUnit({
        unit_code: unitForm.unit_code,
        call_sign: unitForm.call_sign,
        patrol_type: unitForm.patrol_type,
        lead_officer_id: unitForm.lead_officer_id ? parseInt(unitForm.lead_officer_id) : null,
        is_available: unitForm.is_available,
      });
      setSuccess(`Patrol Unit ${unitForm.unit_code} registered successfully!`);
      setShowCreateUnitModal(false);
      setUnitForm({ unit_code: '', call_sign: '', patrol_type: 'CAR', lead_officer_id: '', is_available: true });
      fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create patrol unit');
    }
  };

  const handleManualAssign = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await patrolsApi.createManualAssignment({
        patrol_unit_id: parseInt(manualAssignForm.patrol_unit_id),
        officer_id: parseInt(manualAssignForm.officer_id),
        prp_id: parseInt(manualAssignForm.prp_id),
        shift: manualAssignForm.shift,
        notes: manualAssignForm.notes,
      });
      setSuccess('Patrol unit and officer manually assigned to PRP successfully!');
      setShowManualAssignModal(false);
      setManualAssignForm({
        patrol_unit_id: '',
        officer_id: '',
        prp_id: '',
        shift: 'NIGHT',
        notes: '',
      });
      fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create manual assignment');
    }
  };

  const handleAutoAssign = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await patrolsApi.createAutoAssignment({
        shift: autoAssignForm.shift,
        max_radius_km: parseFloat(autoAssignForm.max_radius_km),
      });
      setSuccess(`Auto-assignment completed! Created ${res.assigned_count || 0} assignments.`);
      setShowAutoAssignModal(false);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Auto-assignment failed');
    }
  };

  const handleStatusTransition = async (assignmentId, newStatus) => {
    try {
      await patrolsApi.updateAssignmentStatus(assignmentId, newStatus);
      setSuccess(`Assignment #${assignmentId} transitioned to ${newStatus}`);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to update assignment status to ${newStatus}`);
    }
  };

  return (
    <div className="page-container">
      {/* Top Toolbar */}
      <div className="toolbar-card">
        <div className="filters-row">
          <div className="tab-pill-group">
            <button
              className={`tab-pill ${activeTab === 'units' ? 'active' : ''}`}
              onClick={() => setActiveTab('units')}
            >
              <Truck size={14} />
              <span>Patrol Units ({units.length})</span>
            </button>
            <button
              className={`tab-pill ${activeTab === 'assignments' ? 'active' : ''}`}
              onClick={() => setActiveTab('assignments')}
            >
              <Clock size={14} />
              <span>Assignments ({assignments.length})</span>
            </button>
          </div>

          {activeTab === 'units' ? (
            <div className="filter-group">
              <select
                className="form-control"
                value={unitStatusFilter}
                onChange={(e) => setUnitStatusFilter(e.target.value)}
              >
                <option value="">All Unit Statuses</option>
                <option value="AVAILABLE">Available (Ready)</option>
                <option value="ON_PATROL">On Patrol</option>
                <option value="DISPATCHED">Dispatched (SOS)</option>
                <option value="OFF_DUTY">Off Duty / Unavailable</option>
              </select>
            </div>
          ) : (
            <div className="filter-group">
              <select
                className="form-control"
                value={assignStatusFilter}
                onChange={(e) => setAssignStatusFilter(e.target.value)}
              >
                <option value="">All Assignment States</option>
                <option value="ASSIGNED">ASSIGNED</option>
                <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
                <option value="EN_ROUTE">EN_ROUTE</option>
                <option value="AT_PRP">AT_PRP</option>
                <option value="COMPLETED">COMPLETED</option>
                <option value="CANCELLED">CANCELLED</option>
              </select>
            </div>
          )}

          <button className="btn btn-secondary btn-sm" onClick={fetchData} disabled={loading} title="Refresh">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>

        <div className="actions-row">
          <button className="btn btn-secondary btn-sm" onClick={() => setShowAutoAssignModal(true)}>
            <Zap size={14} color="#7c3aed" />
            <span>Auto-Assign Fleet</span>
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowManualAssignModal(true)}>
            <Plus size={14} />
            <span>Manual Assign</span>
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreateUnitModal(true)}>
            <Truck size={14} />
            <span>Register Unit</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="alert-banner alert-danger">
          <AlertCircle size={18} />
          <div style={{ flex: 1 }}>{error}</div>
          <button className="modal-close" onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      {success && (
        <div className="alert-banner alert-success">
          <CheckCircle size={18} />
          <div style={{ flex: 1 }}>{success}</div>
          <button className="modal-close" onClick={() => setSuccess(null)}><X size={14} /></button>
        </div>
      )}

      {/* TAB 1: PATROL UNITS TABLE */}
      {activeTab === 'units' && (
        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Law Enforcement Patrol Fleet Directory</h3>
              <p className="card-subtitle">Active patrol units, vehicle call signs, and telemetry readiness</p>
            </div>
            <span className="badge badge-light">{units.length} Registered Units</span>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>UNIT CODE</th>
                  <th>CALL SIGN</th>
                  <th>TYPE</th>
                  <th>LEAD OFFICER</th>
                  <th>AVAILABILITY</th>
                  <th>REGISTERED DATE</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '30px' }}>
                      <RefreshCw className="spin" size={24} style={{ margin: '0 auto' }} />
                      <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>Loading patrol units...</p>
                    </td>
                  </tr>
                ) : units.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '30px' }}>
                      <Truck size={28} color="#94a3b8" style={{ margin: '0 auto' }} />
                      <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>No patrol units found. Register a new unit above.</p>
                    </td>
                  </tr>
                ) : (
                  units.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <span className="code-badge" style={{ fontWeight: 700 }}>{u.unit_code}</span>
                      </td>
                      <td>
                        <strong>{u.call_sign || '—'}</strong>
                      </td>
                      <td>
                        <span className="badge badge-secondary">{u.patrol_type || 'CAR'}</span>
                      </td>
                      <td>
                        {u.lead_officer ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <UserCheck size={14} color="#2563eb" />
                            <span>{u.lead_officer.full_name || u.lead_officer.username}</span>
                            <span style={{ fontSize: '11px', color: '#64748b' }}>({u.lead_officer.badge_number})</span>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Unassigned</span>
                        )}
                      </td>
                      <td>
                        {u.status === 'AVAILABLE' ? (
                          <span className="badge badge-success">● AVAILABLE</span>
                        ) : u.status === 'ON_PATROL' ? (
                          <span className="badge badge-warning">● ON PATROL / BUSY</span>
                        ) : u.status === 'DISPATCHED' ? (
                          <span className="badge badge-danger">● DISPATCHED</span>
                        ) : u.status === 'OFF_DUTY' ? (
                          <span className="badge badge-secondary">● OFF DUTY</span>
                        ) : (
                          <span className="badge badge-warning">● {u.status || 'UNAVAILABLE'}</span>
                        )}
                      </td>
                      <td style={{ color: '#64748b', fontSize: '12px' }}>
                        {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: ASSIGNMENTS TABLE */}
      {activeTab === 'assignments' && (
        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Patrol Response Point (PRP) Assignments</h3>
              <p className="card-subtitle">Active and historical patrol assignments across CMA shifts</p>
            </div>
            <span className="badge badge-light">{assignments.length} Total Assignments</span>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>PATROL UNIT</th>
                  <th>TARGET PRP</th>
                  <th>SHIFT</th>
                  <th>STATUS</th>
                  <th>ASSIGNED TIME</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                      <RefreshCw className="spin" size={24} style={{ margin: '0 auto' }} />
                      <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>Loading assignments...</p>
                    </td>
                  </tr>
                ) : assignments.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                      <Clock size={28} color="#94a3b8" style={{ margin: '0 auto' }} />
                      <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>No patrol assignments found for this filter.</p>
                    </td>
                  </tr>
                ) : (
                  assignments.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <span className="code-badge">#{a.id}</span>
                      </td>
                      <td>
                        <strong>{a.patrol_unit?.unit_code || `Unit #${a.patrol_unit_id}`}</strong>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <MapPin size={14} color="#2563eb" />
                          <span style={{ fontWeight: 600 }}>PRP #{a.prp_id}</span>
                          {a.prp?.location_name && (
                            <span style={{ fontSize: '11px', color: '#64748b' }}>({a.prp.location_name})</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-light">{a.shift}</span>
                      </td>
                      <td>
                        <span className={`badge badge-${
                          a.status === 'COMPLETED' ? 'success' :
                          a.status === 'AT_PRP' ? 'primary' :
                          a.status === 'EN_ROUTE' ? 'info' :
                          a.status === 'ACKNOWLEDGED' ? 'primary' :
                          a.status === 'ASSIGNED' ? 'warning' : 'danger'
                        }`}>
                          {a.status}
                        </span>
                      </td>
                      <td style={{ color: '#64748b', fontSize: '12px' }}>
                        {a.assigned_at ? new Date(a.assigned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td>
                        <div className="action-buttons-group">
                          {a.status === 'ASSIGNED' && (
                            <button
                              className="btn btn-secondary btn-xs"
                              onClick={() => handleStatusTransition(a.id, 'ACKNOWLEDGED')}
                            >
                              Acknowledge
                            </button>
                          )}
                          {a.status === 'ACKNOWLEDGED' && (
                            <button
                              className="btn btn-secondary btn-xs"
                              onClick={() => handleStatusTransition(a.id, 'EN_ROUTE')}
                            >
                              En Route
                            </button>
                          )}
                          {a.status === 'EN_ROUTE' && (
                            <button
                              className="btn btn-primary btn-xs"
                              onClick={() => handleStatusTransition(a.id, 'AT_PRP')}
                            >
                              Mark At PRP
                            </button>
                          )}
                          {a.status === 'AT_PRP' && (
                            <button
                              className="btn btn-success btn-xs"
                              onClick={() => handleStatusTransition(a.id, 'COMPLETED')}
                            >
                              Complete
                            </button>
                          )}
                          {['ASSIGNED', 'ACKNOWLEDGED', 'EN_ROUTE'].includes(a.status) && (
                            <button
                              className="btn btn-outline-danger btn-xs"
                              onClick={() => handleStatusTransition(a.id, 'CANCELLED')}
                            >
                              Cancel
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
      )}

      {/* CREATE UNIT MODAL */}
      {showCreateUnitModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-sm">
            <div className="modal-header">
              <h3 className="modal-title">Register Patrol Unit</h3>
              <button className="modal-close" onClick={() => setShowCreateUnitModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreateUnit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Unit Code *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. PATROL-01"
                    value={unitForm.unit_code}
                    onChange={(e) => setUnitForm({ ...unitForm, unit_code: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Call Sign</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Eagle 1"
                    value={unitForm.call_sign}
                    onChange={(e) => setUnitForm({ ...unitForm, call_sign: e.target.value })}
                  />
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Vehicle Type</label>
                    <select
                      className="form-control"
                      value={unitForm.patrol_type}
                      onChange={(e) => setUnitForm({ ...unitForm, patrol_type: e.target.value })}
                    >
                      <option value="CAR">Patrol Car</option>
                      <option value="BIKE">Motorcycle</option>
                      <option value="VAN">Tactical Van</option>
                      <option value="FOOT">Foot Patrol</option>
                    </select>
                  </div>

                  <div className="form-group col">
                    <label>Lead Officer</label>
                    <select
                      className="form-control"
                      value={unitForm.lead_officer_id}
                      onChange={(e) => setUnitForm({ ...unitForm, lead_officer_id: e.target.value })}
                    >
                      <option value="">(None / Unassigned)</option>
                      {officers.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.full_name || o.username} ({o.badge_number})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-group-inline" style={{ marginTop: '8px' }}>
                  <input
                    type="checkbox"
                    id="is_available_unit"
                    checked={unitForm.is_available}
                    onChange={(e) => setUnitForm({ ...unitForm, is_available: e.target.checked })}
                  />
                  <label htmlFor="is_available_unit">Immediately Available for SOS Dispatch</label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateUnitModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Register Unit
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MANUAL ASSIGN MODAL */}
      {showManualAssignModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-sm">
            <div className="modal-header">
              <h3 className="modal-title">Manual Patrol Assignment</h3>
              <button className="modal-close" onClick={() => setShowManualAssignModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleManualAssign}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Select Patrol Unit *</label>
                  <select
                    className="form-control"
                    required
                    value={manualAssignForm.patrol_unit_id}
                    onChange={(e) => setManualAssignForm({ ...manualAssignForm, patrol_unit_id: e.target.value })}
                  >
                    <option value="">-- Choose Patrol Unit --</option>
                    {units.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.unit_code} ({u.call_sign || u.patrol_type || u.unit_type || 'CAR'}) - {u.status === 'AVAILABLE' ? 'AVAILABLE' : u.status || 'BUSY'}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Select Police Officer *</label>
                  <select
                    className="form-control"
                    required
                    value={manualAssignForm.officer_id}
                    onChange={(e) => setManualAssignForm({ ...manualAssignForm, officer_id: e.target.value })}
                  >
                    <option value="">-- Choose Police Officer --</option>
                    {officers.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.full_name || o.username} ({o.badge_number}) - {o.on_duty ? 'ON DUTY' : 'OFF DUTY'}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Target PRP / Station *</label>
                  <select
                    className="form-control"
                    required
                    value={manualAssignForm.prp_id}
                    onChange={(e) => setManualAssignForm({ ...manualAssignForm, prp_id: e.target.value })}
                  >
                    <option value="">-- Choose Active PRP --</option>
                    {activePRPs.map((p) => (
                      <option key={p.id} value={p.id}>
                        PRP #{p.id} - {p.location_name || `Ward ${p.ward_no || p.ward_id || ''}`} (Risk: {(p.risk_score || 0).toFixed(1)})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Deployment Shift</label>
                  <select
                    className="form-control"
                    value={manualAssignForm.shift}
                    onChange={(e) => setManualAssignForm({ ...manualAssignForm, shift: e.target.value })}
                  >
                    <option value="DAY">DAY SHIFT (06:00 - 14:00)</option>
                    <option value="EVENING">EVENING SHIFT (14:00 - 22:00)</option>
                    <option value="NIGHT">NIGHT SHIFT (22:00 - 06:00)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Special Instructions / Notes</label>
                  <textarea
                    className="form-control"
                    rows="2"
                    placeholder="Optional patrol briefing notes..."
                    value={manualAssignForm.notes}
                    onChange={(e) => setManualAssignForm({ ...manualAssignForm, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowManualAssignModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Assign Unit
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AUTO ASSIGN MODAL */}
      {showAutoAssignModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-sm">
            <div className="modal-header">
              <h3 className="modal-title">Automated Fleet Deployment</h3>
              <button className="modal-close" onClick={() => setShowAutoAssignModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleAutoAssign}>
              <div className="modal-body">
                <p style={{ fontSize: '12px', color: '#64748b' }}>
                  The auto-assignment engine matches available patrol units to active PRPs by minimizing travel distance and balancing shift load.
                </p>

                <div className="form-group">
                  <label>Target Shift</label>
                  <select
                    className="form-control"
                    value={autoAssignForm.shift}
                    onChange={(e) => setAutoAssignForm({ ...autoAssignForm, shift: e.target.value })}
                  >
                    <option value="NIGHT">NIGHT SHIFT</option>
                    <option value="EVENING">EVENING SHIFT</option>
                    <option value="DAY">DAY SHIFT</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Max Dispatch Distance (km)</label>
                  <input
                    type="number"
                    step="0.5"
                    className="form-control"
                    value={autoAssignForm.max_radius_km}
                    onChange={(e) => setAutoAssignForm({ ...autoAssignForm, max_radius_km: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAutoAssignModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  <Zap size={14} />
                  <span>Run Auto-Assignment</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
