import React, { useState, useEffect } from 'react';
import { helpPointsApi } from '../services/api';
import LeafletMap from '../components/LeafletMap';
import {
  LifeBuoy,
  Plus,
  Upload,
  RefreshCw,
  MapPin,
  Phone,
  CheckCircle,
  AlertCircle,
  ShieldCheck,
  ShieldAlert,
  Edit2,
  Trash2,
  Power,
  Map as MapIcon,
  Table as TableIcon,
  ExternalLink,
  X,
} from 'lucide-react';

export default function SafeHelpPointsPage() {
  const [points, setPoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // View Mode: 'table' or 'map'
  const [viewMode, setViewMode] = useState('table');

  // Filters
  const [typeFilter, setTypeFilter] = useState('');
  const [verifiedFilter, setVerifiedFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importSummary, setImportSummary] = useState(null);

  // Form State (for Create & Edit)
  const [editingPointId, setEditingPointId] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    facility_type: 'HOSPITAL',
    latitude: 13.0827,
    longitude: 80.2707,
    address: '',
    phone_number: '',
    is_verified: true,
    is_active: true,
  });

  const fetchPoints = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (typeFilter) params.facility_type = typeFilter;
      if (verifiedFilter !== '') params.is_verified = verifiedFilter === 'true';
      if (activeFilter !== '') params.is_active = activeFilter === 'true';
      if (searchQuery) params.search = searchQuery;

      const data = await helpPointsApi.list(params);
      setPoints(Array.isArray(data) ? data : data.items || []);
    } catch (err) {
      console.error('Failed to load help points:', err);
      setError('Failed to fetch Safe Help Points from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPoints();
  }, [typeFilter, verifiedFilter, activeFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchPoints();
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await helpPointsApi.create({
        name: formData.name.trim(),
        facility_type: formData.facility_type.toUpperCase(),
        latitude: parseFloat(formData.latitude),
        longitude: parseFloat(formData.longitude),
        address: formData.address.trim() || null,
        phone_number: formData.phone_number.trim() || null,
        is_verified: formData.is_verified,
        is_active: formData.is_active,
      });
      setSuccess(`Safe Help Point "${formData.name}" added successfully!`);
      setShowCreateModal(false);
      resetForm();
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add safe help point.');
    }
  };

  const openEditModal = (p) => {
    setEditingPointId(p.id);
    setFormData({
      name: p.name,
      facility_type: p.facility_type,
      latitude: p.latitude,
      longitude: p.longitude,
      address: p.address || '',
      phone_number: p.phone_number || '',
      is_verified: p.is_verified,
      is_active: p.is_active,
    });
    setShowEditModal(true);
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await helpPointsApi.update(editingPointId, {
        name: formData.name.trim(),
        facility_type: formData.facility_type.toUpperCase(),
        latitude: parseFloat(formData.latitude),
        longitude: parseFloat(formData.longitude),
        address: formData.address.trim() || null,
        phone_number: formData.phone_number.trim() || null,
        is_verified: formData.is_verified,
        is_active: formData.is_active,
      });
      setSuccess(`Safe Help Point #${editingPointId} updated successfully!`);
      setShowEditModal(false);
      resetForm();
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update safe help point.');
    }
  };

  const handleVerify = async (pointId) => {
    try {
      const res = await helpPointsApi.verify(pointId);
      const isV = res.is_verified;
      setSuccess(`Safe Help Point #${pointId} verification set to ${isV ? 'VERIFIED' : 'PENDING'}.`);
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to toggle verification.');
    }
  };

  const handleToggleActive = async (pointId) => {
    try {
      const res = await helpPointsApi.deactivate(pointId);
      const isAct = res.is_active;
      setSuccess(`Safe Help Point #${pointId} is now ${isAct ? 'ACTIVE' : 'DEACTIVATED'}.`);
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to toggle active status.');
    }
  };

  const handleDelete = async (pointId, name) => {
    if (!window.confirm(`Are you sure you want to permanently delete "${name}"?`)) return;
    try {
      await helpPointsApi.delete(pointId);
      setSuccess(`Safe Help Point #${pointId} deleted successfully.`);
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete safe help point.');
    }
  };

  const handleCsvImport = async (e) => {
    e.preventDefault();
    if (!csvFile) return;

    setImporting(true);
    setError(null);
    setImportSummary(null);
    try {
      const data = new FormData();
      data.append('file', csvFile);
      const result = await helpPointsApi.importCSV(data);
      setImportSummary(result);
      setSuccess(`CSV Import Complete: ${result.imported} imported, ${result.skipped_duplicates} duplicates skipped.`);
      fetchPoints();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to import CSV.');
    } finally {
      setImporting(false);
    }
  };

  const resetForm = () => {
    setEditingPointId(null);
    setFormData({
      name: '',
      facility_type: 'HOSPITAL',
      latitude: 13.0827,
      longitude: 80.2707,
      address: '',
      phone_number: '',
      is_verified: true,
      is_active: true,
    });
  };

  return (
    <div className="page-container">
      {/* Top Toolbar */}
      <div className="toolbar-card">
        <div className="filters-row">
          {/* View Mode Toggle */}
          <div className="tab-pill-group">
            <button
              className={`tab-pill ${viewMode === 'table' ? 'active' : ''}`}
              onClick={() => setViewMode('table')}
            >
              <TableIcon size={14} />
              <span>Table</span>
            </button>
            <button
              className={`tab-pill ${viewMode === 'map' ? 'active' : ''}`}
              onClick={() => setViewMode('map')}
            >
              <MapIcon size={14} />
              <span>Map View</span>
            </button>
          </div>

          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="form-control"
              placeholder="Search name or address..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: '180px' }}
            />
            <button type="submit" className="btn btn-secondary btn-sm">
              Search
            </button>
          </form>

          <div className="filter-group">
            <select
              className="form-control"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">All Facility Types</option>
              <option value="HOSPITAL">Hospital / Health Center</option>
              <option value="POLICE_STATION">Police Station</option>
              <option value="POLICE_BOOTH">Police Booth / Kiosk</option>
              <option value="EMERGENCY_FACILITY">Emergency Facility</option>
            </select>
          </div>

          <div className="filter-group">
            <select
              className="form-control"
              value={verifiedFilter}
              onChange={(e) => setVerifiedFilter(e.target.value)}
            >
              <option value="">All Verifications</option>
              <option value="true">Verified Only</option>
              <option value="false">Pending Verification</option>
            </select>
          </div>

          <button className="btn btn-secondary btn-sm" onClick={fetchPoints} disabled={loading} title="Refresh">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>

        <div className="actions-row">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setImportSummary(null);
              setShowImportModal(true);
            }}
          >
            <Upload size={14} />
            <span>Import CSV</span>
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              resetForm();
              setShowCreateModal(true);
            }}
          >
            <Plus size={14} />
            <span>Add Help Point</span>
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

      {/* MAP VIEW */}
      {viewMode === 'map' && (
        <div className="dashboard-card" style={{ height: '580px', padding: 0, overflow: 'hidden' }}>
          <div className="card-header">
            <div>
              <h3 className="card-title">Interactive Safe Help Point Geographic Network</h3>
              <p className="card-subtitle">{points.length} verified sanctuaries and public safety facilities</p>
            </div>
          </div>
          <div className="card-body" style={{ height: 'calc(100% - 60px)', padding: 0 }}>
            <LeafletMap helpPoints={points} showHelpPoints={true} height="100%" />
          </div>
        </div>
      )}

      {/* TABLE VIEW */}
      {viewMode === 'table' && (
        <div className="dashboard-card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Public Safety Facilities & Sanctuaries</h3>
              <p className="card-subtitle">Verified hospitals, police stations, police booths, and emergency facilities</p>
            </div>
            <span className="badge badge-light">{points.length} Facilities Listed</span>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>FACILITY NAME & ADDRESS</th>
                  <th>TYPE</th>
                  <th>COORDINATES</th>
                  <th>HELPLINE</th>
                  <th>VERIFICATION</th>
                  <th>STATUS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {points.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                      {loading ? (
                        <>
                          <RefreshCw className="spin" size={24} style={{ margin: '0 auto' }} />
                          <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>Loading facilities...</p>
                        </>
                      ) : (
                        <>
                          <LifeBuoy size={28} color="#94a3b8" style={{ margin: '0 auto' }} />
                          <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>No safe help points found matching filters.</p>
                        </>
                      )}
                    </td>
                  </tr>
                ) : (
                  points.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <strong>{p.name}</strong>
                            {p.map_link && (
                              <a
                                href={p.map_link}
                                target="_blank"
                                rel="noreferrer"
                                style={{ color: '#2563eb' }}
                                title="Open in Google Maps"
                              >
                                <ExternalLink size={12} />
                              </a>
                            )}
                          </div>
                          <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                            {p.address || '—'}
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-primary">{p.facility_type}</span>
                      </td>
                      <td style={{ fontFamily: 'monospace', fontSize: '11px', color: '#64748b' }}>
                        {p.latitude?.toFixed(4)}, {p.longitude?.toFixed(4)}
                      </td>
                      <td>
                        {p.phone_number ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontFamily: 'monospace' }}>
                            <Phone size={12} color="#94a3b8" />
                            <span>{p.phone_number}</span>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '11px' }}>No phone</span>
                        )}
                      </td>
                      <td>
                        {p.is_verified ? (
                          <span className="badge badge-success">
                            <ShieldCheck size={12} /> VERIFIED
                          </span>
                        ) : (
                          <span className="badge badge-warning">
                            <ShieldAlert size={12} /> PENDING
                          </span>
                        )}
                      </td>
                      <td>
                        {p.is_active ? (
                          <span className="badge badge-success">ACTIVE</span>
                        ) : (
                          <span className="badge badge-secondary">DEACTIVATED</span>
                        )}
                      </td>
                      <td>
                        <div className="action-buttons-group">
                          <button
                            onClick={() => handleVerify(p.id)}
                            className={`btn btn-xs ${p.is_verified ? 'btn-secondary' : 'btn-success'}`}
                            title={p.is_verified ? 'Mark Pending' : 'Verify Facility'}
                          >
                            {p.is_verified ? 'Unverify' : 'Verify'}
                          </button>

                          <button
                            onClick={() => handleToggleActive(p.id)}
                            className="btn btn-secondary btn-icon btn-xs"
                            title={p.is_active ? 'Deactivate Facility' : 'Reactivate Facility'}
                          >
                            <Power size={12} color={p.is_active ? '#64748b' : '#10b981'} />
                          </button>

                          <button
                            onClick={() => openEditModal(p)}
                            className="btn btn-secondary btn-icon btn-xs"
                            title="Edit Facility"
                          >
                            <Edit2 size={12} color="#2563eb" />
                          </button>

                          <button
                            onClick={() => handleDelete(p.id, p.name)}
                            className="btn btn-secondary btn-icon btn-xs"
                            title="Delete Facility"
                          >
                            <Trash2 size={12} color="#ef4444" />
                          </button>
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

      {/* CREATE MODAL */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 className="modal-title">Add Safe Help Point</h3>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Facility Name *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Apollo Hospital Emergency Room"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Facility Type</label>
                    <select
                      className="form-control"
                      value={formData.facility_type}
                      onChange={(e) => setFormData({ ...formData, facility_type: e.target.value })}
                    >
                      <option value="HOSPITAL">Hospital / Health Center</option>
                      <option value="POLICE_STATION">Police Station</option>
                      <option value="POLICE_BOOTH">Police Booth / Kiosk</option>
                      <option value="EMERGENCY_FACILITY">Emergency Facility</option>
                    </select>
                  </div>

                  <div className="form-group col">
                    <label>Helpline / Phone</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. +91 44 2829 0200"
                      value={formData.phone_number}
                      onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Latitude *</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={formData.latitude}
                      onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                    />
                  </div>

                  <div className="form-group col">
                    <label>Longitude *</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={formData.longitude}
                      onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Address / Street Description</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Street address or landmark"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  />
                </div>

                <div className="form-row" style={{ marginTop: '6px' }}>
                  <div className="form-group-inline">
                    <input
                      type="checkbox"
                      id="create_is_verified"
                      checked={formData.is_verified}
                      onChange={(e) => setFormData({ ...formData, is_verified: e.target.checked })}
                    />
                    <label htmlFor="create_is_verified">Mark Verified for Citizens</label>
                  </div>

                  <div className="form-group-inline">
                    <input
                      type="checkbox"
                      id="create_is_active"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    />
                    <label htmlFor="create_is_active">Facility Active</label>
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Help Point
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {showEditModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 className="modal-title">Edit Safe Help Point #{editingPointId}</h3>
              <button className="modal-close" onClick={() => setShowEditModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleUpdate}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Facility Name *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Facility Type</label>
                    <select
                      className="form-control"
                      value={formData.facility_type}
                      onChange={(e) => setFormData({ ...formData, facility_type: e.target.value })}
                    >
                      <option value="HOSPITAL">Hospital / Health Center</option>
                      <option value="POLICE_STATION">Police Station</option>
                      <option value="POLICE_BOOTH">Police Booth / Kiosk</option>
                      <option value="EMERGENCY_FACILITY">Emergency Facility</option>
                    </select>
                  </div>

                  <div className="form-group col">
                    <label>Helpline / Phone</label>
                    <input
                      type="text"
                      className="form-control"
                      value={formData.phone_number}
                      onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Latitude *</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={formData.latitude}
                      onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                    />
                  </div>

                  <div className="form-group col">
                    <label>Longitude *</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={formData.longitude}
                      onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Address / Street Description</label>
                  <input
                    type="text"
                    className="form-control"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  />
                </div>

                <div className="form-row" style={{ marginTop: '6px' }}>
                  <div className="form-group-inline">
                    <input
                      type="checkbox"
                      id="edit_is_verified"
                      checked={formData.is_verified}
                      onChange={(e) => setFormData({ ...formData, is_verified: e.target.checked })}
                    />
                    <label htmlFor="edit_is_verified">Mark Verified for Citizens</label>
                  </div>

                  <div className="form-group-inline">
                    <input
                      type="checkbox"
                      id="edit_is_active"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    />
                    <label htmlFor="edit_is_active">Facility Active</label>
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Update Facility
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* IMPORT CSV MODAL */}
      {showImportModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 className="modal-title">Import Safe Help Points CSV</h3>
              <button className="modal-close" onClick={() => setShowImportModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCsvImport}>
              <div className="modal-body">
                <p style={{ fontSize: '12px', color: '#64748b' }}>
                  Upload a CSV file containing Safe Help Points. Columns supported: <span className="code-badge">name, facility_type, latitude, longitude, address, phone_number, is_verified, is_active</span>.
                </p>

                <div className="form-group" style={{ marginTop: '10px' }}>
                  <input
                    type="file"
                    accept=".csv"
                    required
                    className="form-control"
                    onChange={(e) => setCsvFile(e.target.files[0])}
                  />
                </div>

                {importSummary && (
                  <div style={{ padding: '10px 12px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '12px' }}>
                    <div style={{ fontWeight: 700, marginBottom: '4px' }}>Batch Ingestion Report:</div>
                    <div>Total Rows: <strong>{importSummary.total_rows}</strong></div>
                    <div style={{ color: '#059669' }}>Imported: <strong>{importSummary.imported}</strong></div>
                    <div style={{ color: '#d97706' }}>Skipped Duplicates: <strong>{importSummary.skipped_duplicates}</strong></div>
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowImportModal(false)}>
                  Close
                </button>
                <button
                  type="submit"
                  disabled={importing || !csvFile}
                  className="btn btn-primary"
                >
                  {importing ? 'Importing Data...' : 'Import Data'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
