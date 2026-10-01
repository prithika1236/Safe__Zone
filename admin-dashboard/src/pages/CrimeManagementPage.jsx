import React, { useState, useEffect } from 'react';
import {
  FileText,
  Plus,
  Upload,
  Search,
  Filter,
  CheckCircle,
  AlertCircle,
  Edit2,
  Trash2,
  Sparkles,
  RefreshCw,
  X,
} from 'lucide-react';
import { crimesApi } from '../services/api';

const CRIME_CATEGORIES = [
  'THEFT',
  'ROBBERY',
  'BURGLARY',
  'ASSAULT',
  'STALKING',
  'VERBAL_ABUSE_THREAT',
  'SEXUAL_HARASSMENT',
  'DOMESTIC_VIOLENCE',
  'KIDNAPPING',
  'FRAUD',
  'CYBERCRIME',
  'VANDALISM',
  'DRUG_RELATED_CRIME',
  'PUBLIC_DISTURBANCE',
  'HOMICIDE',
  'OTHER',
];

export default function CrimeManagementPage() {
  const [crimes, setCrimes] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(15);
  const [loading, setLoading] = useState(false);

  // Filters
  const [filterCategory, setFilterCategory] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterWard, setFilterWard] = useState('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedCrime, setSelectedCrime] = useState(null);

  // Create Form State
  const [createForm, setCreateForm] = useState({
    description: '',
    latitude: 13.0827,
    longitude: 80.2707,
    ward_no: 119,
    zone_no: 'IX',
    zone_name: 'TEYNAMPET',
    occurred_date: new Date().toISOString().split('T')[0],
    occurred_time: '14:30:00',
    crime_category: '',
    severity: 'MEDIUM',
    location_type: 'STREET',
  });
  const [previewResult, setPreviewResult] = useState(null);
  const [previewing, setPreviewing] = useState(false);

  // Verify Form State
  const [verifyForm, setVerifyForm] = useState({
    crime_category: '',
    severity: 'MEDIUM',
  });

  // Import State
  const [importFile, setImportFile] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    fetchCrimes();
  }, [page, filterCategory, filterSeverity, filterStatus, filterWard]);

  const fetchCrimes = async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: limit,
      };
      if (filterCategory) params.crime_category = filterCategory;
      if (filterSeverity) params.severity = filterSeverity;
      if (filterStatus) params.classification_status = filterStatus;
      if (filterWard) params.ward_no = parseInt(filterWard);

      const res = await crimesApi.list(params);
      if (res?.items) {
        setCrimes(res.items);
        setTotalCount(res.total || 0);
      }
    } catch (err) {
      console.error('Failed to load crimes:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePreviewClassify = async () => {
    if (!createForm.description) return;
    setPreviewing(true);
    try {
      const res = await crimesApi.classifyPreview(createForm.description);
      setPreviewResult(res);
      if (!createForm.crime_category) {
        setCreateForm((prev) => ({ ...prev, crime_category: res.predicted_category }));
      }
    } catch (err) {
      console.error('Preview error:', err);
    } finally {
      setPreviewing(false);
    }
  };

  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    try {
      await crimesApi.create(createForm);
      setShowCreateModal(false);
      setCreateForm({
        description: '',
        latitude: 13.0827,
        longitude: 80.2707,
        ward_no: 119,
        zone_no: 'IX',
        zone_name: 'TEYNAMPET',
        occurred_date: new Date().toISOString().split('T')[0],
        occurred_time: '14:30:00',
        crime_category: '',
        severity: 'MEDIUM',
        location_type: 'STREET',
      });
      setPreviewResult(null);
      fetchCrimes();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to create crime incident');
    }
  };

  const handleVerifySubmit = async (e) => {
    e.preventDefault();
    if (!selectedCrime) return;
    try {
      await crimesApi.verify(selectedCrime.id, verifyForm);
      setShowVerifyModal(false);
      setSelectedCrime(null);
      fetchCrimes();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to verify classification');
    }
  };

  const handleDelete = async (crimeId) => {
    if (!window.confirm(`Are you sure you want to delete incident record #${crimeId}?`)) return;
    try {
      await crimesApi.delete(crimeId);
      fetchCrimes();
    } catch (err) {
      alert('Failed to delete incident');
    }
  };

  const handleImportSubmit = async (e) => {
    e.preventDefault();
    if (!importFile) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', importFile);
      const res = await crimesApi.importCSV(formData);
      setImportResult(res);
      fetchCrimes();
    } catch (err) {
      alert(err.response?.data?.detail || 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="page-container">
      {/* Header Actions & Filters Bar */}
      <div className="toolbar-card">
        <div className="filters-row">
          <div className="filter-group">
            <select
              className="form-control"
              value={filterCategory}
              onChange={(e) => { setFilterCategory(e.target.value); setPage(1); }}
            >
              <option value="">All Categories ({CRIME_CATEGORIES.length})</option>
              {CRIME_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <select
              className="form-control"
              value={filterSeverity}
              onChange={(e) => { setFilterSeverity(e.target.value); setPage(1); }}
            >
              <option value="">All Severities</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>

          <div className="filter-group">
            <select
              className="form-control"
              value={filterStatus}
              onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
            >
              <option value="">All DL Statuses</option>
              <option value="AUTO_CLASSIFIED">AUTO_CLASSIFIED</option>
              <option value="REVIEW_REQUIRED">REVIEW_REQUIRED</option>
              <option value="ADMIN_VERIFIED">ADMIN_VERIFIED</option>
            </select>
          </div>

          <div className="filter-group">
            <input
              type="number"
              className="form-control"
              placeholder="Filter Ward No..."
              value={filterWard}
              onChange={(e) => { setFilterWard(e.target.value); setPage(1); }}
              style={{ width: '150px' }}
            />
          </div>

          <button className="btn btn-secondary btn-sm" onClick={fetchCrimes}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>

        <div className="actions-row">
          <button className="btn btn-secondary btn-sm" onClick={() => { setShowImportModal(true); setImportResult(null); }}>
            <Upload size={15} />
            <span>Import CSV</span>
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
            <Plus size={15} />
            <span>Add Incident</span>
          </button>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="dashboard-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>CRIME ID</th>
                <th>CATEGORY & SEVERITY</th>
                <th>DESCRIPTION</th>
                <th>LOCATION</th>
                <th>DATE & SHIFT</th>
                <th>DL STATUS & CONFIDENCE</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                    <RefreshCw className="spin" size={24} style={{ margin: '0 auto' }} />
                    <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>Loading crime records...</p>
                  </td>
                </tr>
              ) : crimes.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                    <AlertCircle size={28} color="#94a3b8" style={{ margin: '0 auto' }} />
                    <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>No matching crime incidents found.</p>
                  </td>
                </tr>
              ) : (
                crimes.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="code-badge">{c.crime_id}</span>
                    </td>
                    <td>
                      <div className="category-cell">
                        <strong>{c.crime_category}</strong>
                        <span className={`badge badge-${c.severity === 'CRITICAL' || c.severity === 'HIGH' ? 'danger' : c.severity === 'MEDIUM' ? 'warning' : 'info'}`}>
                          {c.severity}
                        </span>
                      </div>
                    </td>
                    <td style={{ maxWidth: '280px' }}>
                      <p className="table-desc-text" title={c.description}>{c.description}</p>
                    </td>
                    <td>
                      <div style={{ fontSize: '12px' }}>
                        <div>Ward {c.ward_no} ({c.zone_name})</div>
                        <span style={{ color: '#94a3b8', fontSize: '11px' }}>{c.location_type || 'STREET'}</span>
                      </div>
                    </td>
                    <td>
                      <div style={{ fontSize: '12px' }}>
                        <div>{c.occurred_date}</div>
                        <span className="badge badge-light">{c.time_period || 'ALL'}</span>
                      </div>
                    </td>
                    <td>
                      <div className="dl-cell">
                        <span className={`badge badge-${c.classification_status === 'ADMIN_VERIFIED' ? 'success' : c.classification_status === 'AUTO_CLASSIFIED' ? 'primary' : 'warning'}`}>
                          {c.classification_status || 'AUTO_CLASSIFIED'}
                        </span>
                        {c.confidence !== null && c.confidence !== undefined && (
                          <span className="conf-text">{(c.confidence * 100).toFixed(1)}% Conf</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="action-buttons-group">
                        <button
                          className="btn-icon"
                          title="Verify or Correct Category"
                          onClick={() => {
                            setSelectedCrime(c);
                            setVerifyForm({
                              crime_category: c.crime_category,
                              severity: c.severity,
                            });
                            setShowVerifyModal(true);
                          }}
                        >
                          <CheckCircle size={15} color="#2563eb" />
                        </button>
                        <button
                          className="btn-icon"
                          title="Delete Record"
                          onClick={() => handleDelete(c.id)}
                        >
                          <Trash2 size={15} color="#ef4444" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="table-pagination">
          <span className="pagination-info">
            Showing {(page - 1) * limit + 1} - {Math.min(page * limit, totalCount)} of {totalCount} incidents
          </span>
          <div className="pagination-buttons">
            <button
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span className="page-number-pill">Page {page}</span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page * limit >= totalCount}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* CREATE MODAL */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3>Create Crime Incident & Auto-Classify</h3>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreateSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Incident Description (Text narrative for BiLSTM DL Classifier) *</label>
                  <textarea
                    className="form-control"
                    rows="3"
                    required
                    placeholder="e.g. Complainant reported smartphone stolen from backpack in crowded bus station..."
                    value={createForm.description}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  />
                  <div style={{ marginTop: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={handlePreviewClassify}
                      disabled={previewing || !createForm.description}
                    >
                      <Sparkles size={12} />
                      <span>{previewing ? 'Classifying...' : 'Test BiLSTM Classifier'}</span>
                    </button>
                    {previewResult && (
                      <span className="preview-badge">
                        Prediction: <strong>{previewResult.predicted_category}</strong> ({(previewResult.confidence * 100).toFixed(1)}%)
                      </span>
                    )}
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Crime Category (Auto-classified if blank)</label>
                    <select
                      className="form-control"
                      value={createForm.crime_category}
                      onChange={(e) => setCreateForm({ ...createForm, crime_category: e.target.value })}
                    >
                      <option value="">Auto-Classify via DL</option>
                      {CRIME_CATEGORIES.map((cat) => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group col">
                    <label>Severity</label>
                    <select
                      className="form-control"
                      value={createForm.severity}
                      onChange={(e) => setCreateForm({ ...createForm, severity: e.target.value })}
                    >
                      <option value="CRITICAL">CRITICAL</option>
                      <option value="HIGH">HIGH</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="LOW">LOW</option>
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Latitude *</label>
                    <input
                      type="number"
                      step="0.0001"
                      className="form-control"
                      required
                      value={createForm.latitude}
                      onChange={(e) => setCreateForm({ ...createForm, latitude: parseFloat(e.target.value) })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Longitude *</label>
                    <input
                      type="number"
                      step="0.0001"
                      className="form-control"
                      required
                      value={createForm.longitude}
                      onChange={(e) => setCreateForm({ ...createForm, longitude: parseFloat(e.target.value) })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Ward No *</label>
                    <input
                      type="number"
                      className="form-control"
                      required
                      value={createForm.ward_no}
                      onChange={(e) => setCreateForm({ ...createForm, ward_no: parseInt(e.target.value) })}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group col">
                    <label>Date *</label>
                    <input
                      type="date"
                      className="form-control"
                      required
                      value={createForm.occurred_date}
                      onChange={(e) => setCreateForm({ ...createForm, occurred_date: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Time</label>
                    <input
                      type="time"
                      className="form-control"
                      value={createForm.occurred_time}
                      onChange={(e) => setCreateForm({ ...createForm, occurred_time: e.target.value })}
                    />
                  </div>
                  <div className="form-group col">
                    <label>Location Type</label>
                    <input
                      type="text"
                      className="form-control"
                      value={createForm.location_type}
                      onChange={(e) => setCreateForm({ ...createForm, location_type: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Incident
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* VERIFY / OVERRIDE MODAL */}
      {showVerifyModal && selectedCrime && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-sm">
            <div className="modal-header">
              <h3>Admin Verify & Correction</h3>
              <button className="modal-close" onClick={() => setShowVerifyModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleVerifySubmit}>
              <div className="modal-body">
                <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '12px' }}>
                  Incident: <strong>{selectedCrime.crime_id}</strong><br />
                  Narrative: <em>"{selectedCrime.description}"</em>
                </p>

                <div className="form-group">
                  <label>Verified Crime Category *</label>
                  <select
                    className="form-control"
                    required
                    value={verifyForm.crime_category}
                    onChange={(e) => setVerifyForm({ ...verifyForm, crime_category: e.target.value })}
                  >
                    {CRIME_CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Severity Rating</label>
                  <select
                    className="form-control"
                    value={verifyForm.severity}
                    onChange={(e) => setVerifyForm({ ...verifyForm, severity: e.target.value })}
                  >
                    <option value="CRITICAL">CRITICAL</option>
                    <option value="HIGH">HIGH</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="LOW">LOW</option>
                  </select>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowVerifyModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-success">
                  Confirm Verification (ADMIN_VERIFIED)
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CSV IMPORT MODAL */}
      {showImportModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3>Batch CSV Crime Ingestion</h3>
              <button className="modal-close" onClick={() => setShowImportModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleImportSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Select CSV Dataset File (safezone_crime_dataset.csv)</label>
                  <input
                    type="file"
                    accept=".csv"
                    className="form-control"
                    required
                    onChange={(e) => setImportFile(e.target.files[0])}
                  />
                  <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '6px' }}>
                    Columns required: crime_id, description, crime_category, severity, latitude, longitude, ward_no, zone_no, zone_name, occurred_date, occurred_time, time_period, location_type, reported_date, status.
                  </p>
                </div>

                {importResult && (
                  <div className="alert alert-success" style={{ marginTop: '12px', fontSize: '12px' }}>
                    <strong>Import Succeeded:</strong><br />
                    • Records Imported: <strong>{importResult.imported}</strong><br />
                    • Duplicates Skipped: <strong>{importResult.skipped_duplicates}</strong><br />
                    • Errors: <strong>{importResult.errors?.length || 0}</strong>
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowImportModal(false)}>
                  Close
                </button>
                <button type="submit" className="btn btn-primary" disabled={importing || !importFile}>
                  {importing ? 'Processing Ingestion...' : 'Upload & Ingest'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
