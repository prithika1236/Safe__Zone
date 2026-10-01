import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach Authorization Token if available
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('safezone_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ==========================================
// API SERVICE MODULES
// ==========================================

export const authApi = {
  login: async (email, password) => {
    const res = await apiClient.post('/auth/login', { email, password });
    if (res.data?.access_token) {
      localStorage.setItem('safezone_token', res.data.access_token);
      localStorage.setItem('safezone_user', JSON.stringify(res.data.user));
    }
    return res.data;
  },
  me: () => apiClient.get('/auth/me').then((r) => r.data),
  logout: () => {
    localStorage.removeItem('safezone_token');
    localStorage.removeItem('safezone_user');
  },
};

export const crimesApi = {
  list: (params) => apiClient.get('/crimes/', { params }).then((r) => r.data),
  get: (id) => apiClient.get(`/crimes/${id}`).then((r) => r.data),
  create: (data) => apiClient.post('/crimes/', data).then((r) => r.data),
  update: (id, data) => apiClient.put(`/crimes/${id}`, data).then((r) => r.data),
  delete: (id) => apiClient.delete(`/crimes/${id}`).then((r) => r.data),
  verify: (id, data) => apiClient.post(`/crimes/${id}/verify`, data).then((r) => r.data),
  classifyPreview: (description) => apiClient.post('/crimes/classify-preview', { description }).then((r) => r.data),
  importCSV: (formData) =>
    apiClient.post('/crimes/import-csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
};

export const riskApi = {
  getWards: (params) => apiClient.get('/risk/wards', { params }).then((r) => r.data),
  getSingleWard: (wardNo, params) => apiClient.get(`/risk/wards/${wardNo}`, { params }).then((r) => r.data),
  calculate: (data) => apiClient.post('/risk/calculate', data).then((r) => r.data),
  pointRisk: (data) => apiClient.post('/risk/point-risk', data).then((r) => r.data),
  getGeoJSON: (params) => apiClient.get('/risk/geojson', { params }).then((r) => r.data),
};

export const prpApi = {
  optimize: (data) => apiClient.post('/prp/optimize', data).then((r) => r.data),
  createRun: (data) => apiClient.post('/prp/runs', data).then((r) => r.data),
  listRuns: (params) => apiClient.get('/prp/runs', { params }).then((r) => r.data),
  getRun: (id) => apiClient.get(`/prp/runs/${id}`).then((r) => r.data),
  updateStatus: (id, status) => apiClient.post(`/prp/${id}/status`, { status }).then((r) => r.data),
  getActive: () => apiClient.get('/prp/active').then((r) => r.data),
};

export const policeApi = {
  createOfficer: (data) => apiClient.post('/admin/police', data).then((r) => r.data),
  listOfficers: (params) => apiClient.get('/admin/police', { params }).then((r) => r.data),
  updateOfficer: (id, data) => apiClient.put(`/admin/police/${id}`, data).then((r) => r.data),
  createUnit: (data) => apiClient.post('/admin/patrol-units', data).then((r) => r.data),
  listUnits: (params) => apiClient.get('/admin/patrol-units', { params }).then((r) => r.data),
  updateUnit: (id, data) => apiClient.put(`/admin/patrol-units/${id}`, data).then((r) => r.data),
};

export const patrolsApi = {
  createManualAssignment: (data) => apiClient.post('/patrols/assignments/manual', data).then((r) => r.data),
  createAutoAssignment: (data) => apiClient.post('/patrols/assignments/auto', data).then((r) => r.data),
  listAssignments: (params) => apiClient.get('/patrols/assignments', { params }).then((r) => r.data),
  updateAssignmentStatus: (id, status) => apiClient.post(`/patrols/assignments/${id}/status`, { status }).then((r) => r.data),
  acknowledge: (id) => apiClient.post(`/patrols/assignments/${id}/acknowledge`).then((r) => r.data),
  markAtPRP: (id) => apiClient.post(`/patrols/assignments/${id}/at-prp`).then((r) => r.data),
  complete: (id) => apiClient.post(`/patrols/assignments/${id}/complete`).then((r) => r.data),
};

export const helpPointsApi = {
  list: (params) => apiClient.get('/help-points/', { params }).then((r) => r.data).catch(() => []),
  create: (data) => apiClient.post('/help-points/', data).then((r) => r.data),
  update: (id, data) => apiClient.put(`/help-points/${id}`, data).then((r) => r.data),
  delete: (id) => apiClient.delete(`/help-points/${id}`).then((r) => r.data),
  verify: (id) => apiClient.post(`/help-points/${id}/verify`).then((r) => r.data),
  deactivate: (id) => apiClient.post(`/help-points/${id}/deactivate`).then((r) => r.data),
  importCSV: (formData) =>
    apiClient.post('/help-points/import-csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
};


export const sosApi = {
  list: (params) => apiClient.get('/sos/active', { params }).then((r) => r.data).catch(() => []),
  getHistory: (params) => apiClient.get('/sos/admin/history', { params }).then((r) => r.data).catch(() => []),
  updateStatus: (id, status) => apiClient.post(`/sos/${id}/status`, { status }),
  dispatch: (id, patrolUnitId) => apiClient.post(`/sos/${id}/dispatch`, { patrol_unit_id: patrolUnitId }),
};

export const analyticsApi = {
  getSummary: () => apiClient.get('/analytics/summary').then((r) => r.data).catch(() => null),
  evaluate: (data) => apiClient.post('/analytics/evaluate', data).then((r) => r.data),
};

export default apiClient;


