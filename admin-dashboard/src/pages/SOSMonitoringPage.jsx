import React, { useState, useEffect } from 'react';
import { sosApi, policeApi } from '../services/api';
import {
  AlertTriangle,
  Radio,
  Phone,
  MapPin,
  Clock,
  Shield,
  CheckCircle,
  RefreshCw,
  AlertCircle,
  User,
  Zap,
  X,
  History,
  CheckCheck,
} from 'lucide-react';

export default function SOSMonitoringPage() {
  const [activeTab, setActiveTab] = useState('active'); // 'active' | 'history'
  const [alerts, setAlerts] = useState([]);
  const [patrolUnits, setPatrolUnits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Dispatch Modal
  const [dispatchAlert, setDispatchAlert] = useState(null);
  const [selectedUnitId, setSelectedUnitId] = useState('');

  const fetchAlerts = async () => {
    setLoading(true);
    setError(null);
    try {
      if (activeTab === 'active') {
        const [sosRes, unitsRes] = await Promise.all([
          sosApi.list().catch(() => []),
          policeApi.listUnits({ is_available: true }).catch(() => ({ items: [] })),
        ]);

        const sosList = Array.isArray(sosRes) ? sosRes : (sosRes.items || []);
        const unitList = Array.isArray(unitsRes) ? unitsRes : (unitsRes.items || []);
        setAlerts(sosList);
        setPatrolUnits(unitList);
      } else {
        const histRes = await sosApi.getHistory().catch(() => []);
        const histList = Array.isArray(histRes) ? histRes : (histRes.items || []);
        setAlerts(histList);
      }
    } catch (err) {
      console.error('Failed to load SOS alerts:', err);
      setError('Failed to fetch emergency SOS signals.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    // 15-second heartbeat poll for live SOS monitoring when in active tab
    const interval = setInterval(() => {
      if (activeTab === 'active') {
        fetchAlerts();
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [activeTab]);

  const handleDispatch = async (e) => {
    e.preventDefault();
    if (!dispatchAlert || !selectedUnitId) return;

    try {
      await sosApi.dispatch(dispatchAlert.id, parseInt(selectedUnitId));
      setSuccess(`Patrol Unit #${selectedUnitId} dispatched to SOS #${dispatchAlert.id}!`);
      setDispatchAlert(null);
      setSelectedUnitId('');
      fetchAlerts();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to dispatch patrol unit.');
    }
  };

  const handleUpdateStatus = async (alertId, status) => {
    try {
      await sosApi.updateStatus(alertId, status);
      setSuccess(`SOS #${alertId} updated to ${status}.`);
      fetchAlerts();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to update SOS #${alertId}`);
    }
  };

  // Active counts
  const triggeredCount = alerts.filter((a) => a.status === 'TRIGGERED' || a.status === 'PENDING' || a.status === 'ACTIVE').length;
  const inProgressCount = alerts.filter((a) => a.status === 'DISPATCHED' || a.status === 'ASSIGNED' || a.status === 'ACCEPTED' || a.status === 'EN_ROUTE' || a.status === 'ARRIVED').length;
  const noPatrolCount = alerts.filter((a) => a.status === 'NO_AVAILABLE_PATROL').length;

  // History counts
  const resolvedCount = alerts.filter((a) => a.status === 'RESOLVED').length;
  const cancelledCount = alerts.filter((a) => a.status === 'CANCELLED').length;

  return (
    <div className="page-container">
      {/* Top Toolbar */}
      <div className="toolbar-card">
        <div className="filters-row">
          <div className="tab-pill-group">
            <button
              className={`tab-pill ${activeTab === 'active' ? 'active' : ''}`}
              onClick={() => setActiveTab('active')}
            >
              <Radio size={14} />
              <span>ACTIVE SOS</span>
            </button>
            <button
              className={`tab-pill ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              <History size={14} />
              <span>HISTORY</span>
            </button>
          </div>

          {activeTab === 'active' ? (
            <span className="badge badge-light" style={{ marginLeft: '12px' }}>
              {triggeredCount} Active Distress • {inProgressCount} In Progress {noPatrolCount > 0 ? `• ${noPatrolCount} No Patrol` : ''}
            </span>
          ) : (
            <span className="badge badge-light" style={{ marginLeft: '12px' }}>
              {alerts.length} Total Incidents • {resolvedCount} Resolved • {cancelledCount} Cancelled
            </span>
          )}
        </div>

        <div className="actions-row">
          <button className="btn btn-secondary btn-sm" onClick={fetchAlerts} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>{activeTab === 'active' ? 'Live Refresh' : 'Refresh History'}</span>
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

      {/* Alerts Grid */}
      <div className="sos-grid">
        {alerts.length === 0 ? (
          <div className="dashboard-card" style={{ gridColumn: '1 / -1', padding: '48px 24px', textAlign: 'center' }}>
            <div className="empty-state">
              <Shield size={42} color="#10b981" />
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#1e293b' }}>
                {activeTab === 'active'
                  ? 'All Clear — No Active SOS Distress Calls'
                  : 'No Historical SOS Records Found'}
              </h3>
              <p style={{ color: '#64748b' }}>
                {activeTab === 'active'
                  ? 'Live monitoring is running. Distress signals broadcast from citizen apps will appear here instantly.'
                  : 'Historical and resolved emergency incidents will be displayed here for administrative auditing.'}
              </p>
            </div>
          </div>
        ) : (
          alerts.map((item) => {
            const isTerminal = item.status === 'RESOLVED' || item.status === 'CANCELLED';
            const isDispatched = item.status === 'DISPATCHED' || item.status === 'ASSIGNED' || item.status === 'ACCEPTED' || item.status === 'EN_ROUTE' || item.status === 'ARRIVED';

            return (
              <div
                key={item.id}
                className={`sos-card ${
                  item.status === 'TRIGGERED' || item.status === 'PENDING'
                    ? 'sos-card-triggered'
                    : isDispatched
                    ? 'sos-card-dispatched'
                    : item.status === 'RESOLVED'
                    ? 'sos-card-resolved'
                    : ''
                }`}
              >
                <div className="sos-header">
                  <span
                    className={`sos-badge-pulse ${
                      item.status === 'TRIGGERED' || item.status === 'PENDING'
                        ? 'sos-badge-triggered'
                        : isDispatched
                        ? 'sos-badge-dispatched'
                        : 'sos-badge-resolved'
                    }`}
                  >
                    <Radio size={12} />
                    {item.status}
                  </span>
                  <span style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={12} />
                    {item.triggered_at
                      ? new Date(item.triggered_at).toLocaleString()
                      : item.created_at
                      ? new Date(item.created_at).toLocaleString()
                      : 'Recent'}
                  </span>
                </div>

                <div className="sos-body">
                  <div className="sos-detail-row" style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                    <User size={16} />
                    <span>{item.citizen_name || `Citizen Distress #${item.id}`}</span>
                  </div>

                  {item.phone && (
                    <div className="sos-detail-row">
                      <Phone size={14} />
                      <a href={`tel:${item.phone}`} style={{ color: '#2563eb', fontWeight: 600, fontFamily: 'monospace' }}>
                        {item.phone}
                      </a>
                    </div>
                  )}

                  <div className="sos-detail-row" style={{ alignItems: 'flex-start' }}>
                    <MapPin size={14} color="#dc2626" style={{ marginTop: '2px' }} />
                    <div>
                      <div style={{ fontWeight: 600 }}>{item.address || `Emergency Coordinates`}</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
                        {item.latitude?.toFixed(5)}, {item.longitude?.toFixed(5)}
                      </div>
                    </div>
                  </div>

                  {(item.assigned_officer_id || item.assigned_patrol_id) && (
                    <div className="sos-detail-row" style={{ fontSize: '12px', color: '#334155' }}>
                      <Shield size={14} color="#0284c7" />
                      <span>
                        Assigned: {item.assigned_officer_id ? `Officer #${item.assigned_officer_id}` : ''}
                        {item.assigned_officer_id && item.assigned_patrol_id ? ' • ' : ''}
                        {item.assigned_patrol_id ? `Patrol #${item.assigned_patrol_id}` : ''}
                      </span>
                    </div>
                  )}

                  {item.resolved_at && (
                    <div className="sos-detail-row" style={{ fontSize: '11px', color: '#16a34a' }}>
                      <CheckCheck size={14} />
                      <span>Resolved At: {new Date(item.resolved_at).toLocaleString()}</span>
                    </div>
                  )}

                  {item.notes && (
                    <div style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '12px', fontStyle: 'italic', color: '#475569' }}>
                      "{item.notes}"
                    </div>
                  )}
                </div>

                {/* Actions (Only for non-terminal active view) */}
                {activeTab === 'active' && !isTerminal ? (
                  <div className="sos-actions">
                    {(item.status === 'TRIGGERED' || item.status === 'PENDING' || item.status === 'NO_AVAILABLE_PATROL') && (
                      <button
                        className="btn btn-danger btn-sm"
                        style={{ flex: 1 }}
                        onClick={() => {
                          setDispatchAlert(item);
                          setSelectedUnitId(patrolUnits[0]?.id || '');
                        }}
                      >
                        <Zap size={14} />
                        <span>Dispatch Patrol Unit</span>
                      </button>
                    )}

                    {isDispatched && (
                      <button
                        className="btn btn-success btn-sm"
                        style={{ flex: 1 }}
                        onClick={() => handleUpdateStatus(item.id, 'RESOLVED')}
                      >
                        <CheckCircle size={14} />
                        <span>Mark Resolved</span>
                      </button>
                    )}

                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleUpdateStatus(item.id, 'CANCELLED')}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="sos-actions" style={{ justifyContent: 'flex-end' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '4px 8px',
                        borderRadius: '4px',
                        backgroundColor: item.status === 'RESOLVED' ? '#ecfdf5' : '#f1f5f9',
                        color: item.status === 'RESOLVED' ? '#047857' : '#64748b',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      {item.status === 'RESOLVED' ? <CheckCheck size={12} /> : <X size={12} />}
                      {item.status === 'RESOLVED' ? 'Incident Resolved' : 'Incident Cancelled'}
                    </span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* DISPATCH UNIT MODAL */}
      {dispatchAlert && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-sm">
            <div className="modal-header">
              <h3 className="modal-title" style={{ color: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <AlertTriangle size={18} />
                Dispatch Emergency Unit
              </h3>
              <button className="modal-close" onClick={() => setDispatchAlert(null)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleDispatch}>
              <div className="modal-body">
                <div style={{ padding: '10px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', fontSize: '12px', color: '#991b1b' }}>
                  <strong>Distress Incident #{dispatchAlert.id}:</strong><br />
                  Citizen: {dispatchAlert.citizen_name || 'Emergency Distress'}<br />
                  Location: <span style={{ fontFamily: 'monospace' }}>{dispatchAlert.latitude?.toFixed(5)}, {dispatchAlert.longitude?.toFixed(5)}</span>
                </div>

                <div className="form-group">
                  <label>Select Available Patrol Unit *</label>
                  <select
                    required
                    className="form-control"
                    value={selectedUnitId}
                    onChange={(e) => setSelectedUnitId(e.target.value)}
                  >
                    <option value="">-- Choose Patrol Unit --</option>
                    {patrolUnits.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.unit_code} ({u.call_sign || u.patrol_type}) - READY
                      </option>
                    ))}
                  </select>
                  {patrolUnits.length === 0 && (
                    <p style={{ fontSize: '11px', color: '#b45309', marginTop: '4px' }}>
                      No available patrol units detected. Please free an on-duty unit in Patrols tab.
                    </p>
                  )}
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setDispatchAlert(null)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!selectedUnitId}
                  className="btn btn-danger"
                >
                  <Zap size={14} />
                  Confirm Dispatch
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
