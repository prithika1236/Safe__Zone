import React, { useState, useEffect } from 'react';
import { policeApi } from '../services/api';
import {
  Users,
  UserPlus,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Phone,
  Mail,
  Award,
  X,
} from 'lucide-react';

export default function PolicePage() {
  const [officers, setOfficers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Filters
  const [activeFilter, setActiveFilter] = useState('');
  const [rankFilter, setRankFilter] = useState('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    badge_number: '',
    rank: 'OFFICER',
    phone_number: '',
    assigned_station: '',
    is_active: true,
  });

  const fetchOfficers = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (activeFilter !== '') params.is_active = activeFilter === 'true';
      if (rankFilter) params.rank = rankFilter;

      const data = await policeApi.listOfficers(params);
      setOfficers(data.items || data || []);
    } catch (err) {
      console.error('Failed to load officers:', err);
      setError('Failed to fetch police officer records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOfficers();
  }, [activeFilter, rankFilter]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await policeApi.createOfficer(formData);
      setSuccess(`Officer ${formData.full_name} (${formData.badge_number}) registered successfully!`);
      setShowCreateModal(false);
      setFormData({
        username: '',
        email: '',
        password: '',
        full_name: '',
        badge_number: '',
        rank: 'OFFICER',
        phone_number: '',
        assigned_station: '',
        is_active: true,
      });
      fetchOfficers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to register officer.');
    }
  };

  const handleToggleActive = async (officer) => {
    try {
      await policeApi.updateOfficer(officer.id, {
        is_active: !officer.is_active,
      });
      setSuccess(`Officer ${officer.full_name || officer.username} ${!officer.is_active ? 'activated' : 'deactivated'}.`);
      fetchOfficers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update officer status.');
    }
  };

  return (
    <div className="page-container">
      {/* Top Toolbar */}
      <div className="toolbar-card">
        <div className="filters-row">
          <div className="filter-group">
            <select
              className="form-control"
              value={activeFilter}
              onChange={(e) => setActiveFilter(e.target.value)}
            >
              <option value="">All Officer Accounts</option>
              <option value="true">Active Accounts Only</option>
              <option value="false">Deactivated Only</option>
            </select>
          </div>

          <div className="filter-group">
            <select
              className="form-control"
              value={rankFilter}
              onChange={(e) => setRankFilter(e.target.value)}
            >
              <option value="">All Ranks</option>
              <option value="CONSTABLE">Constable</option>
              <option value="HEAD_CONSTABLE">Head Constable</option>
              <option value="ASI">Assistant Sub-Inspector (ASI)</option>
              <option value="SI">Sub-Inspector (SI)</option>
              <option value="INSPECTOR">Inspector</option>
              <option value="DSP">DSP / ACP</option>
            </select>
          </div>

          <button className="btn btn-secondary btn-sm" onClick={fetchOfficers} disabled={loading} title="Refresh">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>

        <div className="actions-row">
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
            <UserPlus size={14} />
            <span>Onboard Officer</span>
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

      {/* Officers Table Card */}
      <div className="dashboard-card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Law Enforcement Officer Roster</h3>
            <p className="card-subtitle">Manage officer credentials, station jurisdictions, and access controls</p>
          </div>
          <span className="badge badge-light">{officers.length} Registered Officers</span>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>BADGE NO.</th>
                <th>OFFICER NAME & USERNAME</th>
                <th>RANK & STATION</th>
                <th>CONTACT DETAILS</th>
                <th>STATUS</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: '30px' }}>
                    <RefreshCw className="spin" size={24} style={{ margin: '0 auto' }} />
                    <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>Loading officers...</p>
                  </td>
                </tr>
              ) : officers.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: '30px' }}>
                    <Users size={28} color="#94a3b8" style={{ margin: '0 auto' }} />
                    <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>No officer records found.</p>
                  </td>
                </tr>
              ) : (
                officers.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Award size={14} color="#2563eb" />
                        <span className="code-badge" style={{ fontWeight: 700 }}>
                          {o.badge_number || 'N/A'}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div>
                        <strong>{o.full_name || o.username}</strong>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>@{o.username}</div>
                      </div>
                    </td>
                    <td>
                      <div>
                        <span className="badge badge-secondary">{o.rank || 'OFFICER'}</span>
                        <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                          {o.station_name || o.assigned_station || '—'}
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ fontSize: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Mail size={12} color="#94a3b8" />
                          <span>{o.email}</span>
                        </div>
                        {o.phone_number && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#64748b', marginTop: '2px' }}>
                            <Phone size={12} color="#94a3b8" />
                            <span>{o.phone_number}</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                        {/* 1. Account Access Status */}
                        {o.is_active ? (
                          <span className="badge badge-success" style={{ fontSize: '10px', padding: '2px 6px' }}>
                            <ShieldCheck size={11} /> ACTIVE ACC
                          </span>
                        ) : (
                          <span className="badge badge-secondary" style={{ fontSize: '10px', padding: '2px 6px' }}>
                            DEACTIVATED
                          </span>
                        )}

                        {/* 2. Operational Duty & Availability */}
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {o.on_duty ? (
                            <>
                              <span className="badge badge-info" style={{ fontSize: '10px', padding: '2px 6px' }}>
                                ● ON DUTY
                              </span>
                              {o.is_available ? (
                                <span className="badge badge-success" style={{ fontSize: '10px', padding: '2px 6px' }}>
                                  AVAILABLE
                                </span>
                              ) : (
                                <span className="badge badge-warning" style={{ fontSize: '10px', padding: '2px 6px' }}>
                                  BUSY
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="badge badge-secondary" style={{ fontSize: '10px', padding: '2px 6px', opacity: 0.8 }}>
                              ○ OFF DUTY
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <button
                        onClick={() => handleToggleActive(o)}
                        className={`btn btn-xs ${o.is_active ? 'btn-outline-danger' : 'btn-success'}`}
                      >
                        {o.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ONBOARD OFFICER MODAL */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 className="modal-title">Onboard Police Officer</h3>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group col">
                    <label>Username *</label>
                    <input
                      type="text"
                      required
                      className="form-control"
                      placeholder="e.g. officer_john"
                      value={formData.username}
                      onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Email *</label>
                    <input
                      type="email"
                      required
                      className="form-control"
                      placeholder="officer@safezone.gov"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Initial Password *</label>
                    <input
                      type="password"
                      required
                      className="form-control"
                      placeholder="••••••••"
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Full Name *</label>
                    <input
                      type="text"
                      required
                      className="form-control"
                      placeholder="e.g. John Doe"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Badge Number *</label>
                    <input
                      type="text"
                      required
                      className="form-control"
                      placeholder="e.g. POL-8891"
                      value={formData.badge_number}
                      onChange={(e) => setFormData({ ...formData, badge_number: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Rank</label>
                    <select
                      className="form-control"
                      value={formData.rank}
                      onChange={(e) => setFormData({ ...formData, rank: e.target.value })}
                    >
                      <option value="CONSTABLE">Constable</option>
                      <option value="HEAD_CONSTABLE">Head Constable</option>
                      <option value="ASI">Assistant Sub-Inspector (ASI)</option>
                      <option value="SI">Sub-Inspector (SI)</option>
                      <option value="INSPECTOR">Inspector</option>
                      <option value="DSP">DSP / ACP</option>
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Assigned Station / Ward</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. Ward 119 Station"
                      value={formData.assigned_station}
                      onChange={(e) => setFormData({ ...formData, assigned_station: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Phone Number</label>
                    <input
                      type="tel"
                      className="form-control"
                      placeholder="+91 9876543210"
                      value={formData.phone_number}
                      onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group-inline" style={{ marginTop: '8px' }}>
                  <input
                    type="checkbox"
                    id="officer_active_check"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                  <label htmlFor="officer_active_check">Set account as Active immediately</label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Onboard Officer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
