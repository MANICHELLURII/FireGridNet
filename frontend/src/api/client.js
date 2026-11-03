import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

const responseCache = new Map();

function cachedRequest(key, ttlMs, request) {
  const current = responseCache.get(key);
  if (current?.promise) return current.promise;
  if (current && current.expiresAt > Date.now()) return Promise.resolve(current.data);

  const promise = request()
    .then((data) => {
      responseCache.set(key, { data, expiresAt: Date.now() + ttlMs });
      return data;
    })
    .catch((error) => {
      responseCache.delete(key);
      throw error;
    });
  responseCache.set(key, { promise, expiresAt: 0 });
  return promise;
}

export const getCachedValue = (key) => {
  const cached = responseCache.get(key);
  return cached && !cached.promise && cached.expiresAt > Date.now() ? cached.data : undefined;
};

export const getGridCells = () =>
  cachedRequest("grid-cells", 30 * 60_000, () => api.get("/grid/cells").then((r) => r.data));

export const getCellRisk = (cellId) =>
  cachedRequest(`cell-risk:${cellId}`, 30 * 60_000, () =>
    api.get(`/grid/${cellId}/risk`).then((r) => r.data).catch((error) => {
      if (error.response?.status === 404) return null;
      throw error;
    })
  );

export const getCellDetails = (cellId) =>
  cachedRequest(`cell-details:${cellId}`, 60_000, () => api.get(`/grid/${cellId}/details`).then((r) => r.data));

export const getRegionalRiskScore = () =>
  cachedRequest("regional-risk-score", 60_000, () => api.get("/grid/overview/risk-score").then((r) => r.data));

export const getForestVulnerability = () =>
  cachedRequest("forest-vulnerability", 60_000, () => api.get("/grid/overview/vulnerability").then((r) => r.data));

export const getNeighborExposure = (cellId) =>
  cachedRequest(`neighbor-exposure:${cellId}`, 60_000, () => api.get(`/grid/${cellId}/neighbor-exposure`).then((r) => r.data));

export const getCellRiskHistory = (cellId, days = 14) =>
  cachedRequest(`risk-history:${cellId}:${days}`, 60_000, () =>
    api.get(`/grid/${cellId}/risk-history`, { params: { days } }).then((r) => r.data)
  );

export const getRecentPredictions = ({ limit = 25, offset = 0, descending = true } = {}) =>
  api.get("/grid/overview/predictions", { params: { limit, offset, descending } }).then((r) => r.data);

export const getCellForecast = (cellId) =>
  cachedRequest(`cell-forecast:${cellId}`, 30 * 60_000, () => api.get(`/grid/${cellId}/forecast`).then((r) => r.data));

export const getCellVulnerability = (cellId) =>
  cachedRequest(`cell-vulnerability:${cellId}`, 60_000, () => api.get(`/grid/${cellId}/vulnerability`).then((r) => r.data));

export const getAlerts = (limit = 50) =>
  api.get("/alerts", { params: { limit } }).then((r) => r.data);

export const getRecentDetections = (params = {}) =>
  api.get("/detections/recent", { params }).then((r) => r.data);

export const updateDetectionStatus = (cellId, detectionId, status) =>
  api.patch(`/grid/${cellId}/detections/${detectionId}/status`, { status }).then((r) => r.data);

export const getReportSnapshot = () => api.get("/reports/snapshot").then((r) => r.data);

export const getReportTrend = (days = 14) => api.get("/reports/trend", { params: { days } }).then((r) => r.data);

export const getReportEvaluation = () => api.get("/reports/evaluation").then((r) => r.data);

export const getDashboardSummary = () =>
  cachedRequest("dashboard-summary", 60_000, () => api.get("/dashboard/summary").then((r) => r.data));

export const predictRisk = (cellId, features) =>
  api.post(`/predict-risk/${cellId}`, features).then((r) => r.data);

export default api;
