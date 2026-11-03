import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getRecentDetections, updateDetectionStatus } from "../api/client";

const STATUSES = ["unverified", "confirmed", "false_positive", "resolved"];
const SOURCE_LABELS = {
  nasa_firms: "NASA FIRMS",
  satellite: "Satellite",
  yolo_upload: "YOLO image upload",
  yolo: "YOLO image upload",
  aerial: "Aerial imagery",
  drone: "Drone",
  webcam: "Webcam",
};
const STATUS_LABELS = { unverified: "Unverified", confirmed: "Confirmed", false_positive: "False positive", resolved: "Resolved" };
const sourceLabel = (source) => SOURCE_LABELS[source] || String(source || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const formatTimestamp = (value) => value ? new Date(value).toLocaleString() : "—";
const confidenceLabel = (value) => value == null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;

export default function FireDetections() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ source: "", status: "", date_from: "", date_to: "" });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatingId, setUpdatingId] = useState("");
  const [statusError, setStatusError] = useState("");

  const query = useMemo(() => Object.fromEntries(Object.entries({ limit: 50, ...filters }).filter(([, value]) => value !== "")), [filters]);
  const loadRows = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const result = await getRecentDetections(query);
      setRows(result);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Unable to load detections.");
    } finally {
      if (isInitial) setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    let timer;
    const refreshIfVisible = () => {
      if (document.visibilityState === "visible") loadRows(true);
    };
    refreshIfVisible();
    timer = window.setInterval(() => {
      if (document.visibilityState === "visible") loadRows(false);
    }, 60_000);
    document.addEventListener("visibilitychange", refreshIfVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshIfVisible);
    };
  }, [loadRows]);

  const sources = useMemo(() => [...new Set(rows.map((row) => row.source).filter(Boolean))].sort(), [rows]);
  const updateStatus = async (row, status) => {
    setUpdatingId(row.id);
    setStatusError("");
    try {
      const updated = await updateDetectionStatus(row.cell_id, row.id, status);
      setRows((current) => current.map((item) => item.id === row.id ? { ...item, ...updated } : item));
    } catch (err) {
      setStatusError(err.response?.data?.detail || err.message || "Unable to update detection status.");
    } finally {
      setUpdatingId("");
    }
  };
  const openCell = (row) => {
    if (row.cell_id) navigate("/live-map", { state: { focusCellId: row.cell_id } });
  };

  return (
    <section className="fire-detections-page">
      <div className="detections-intro">
        <div><h2>Detection feed</h2><p>Review recent fire and smoke detections from connected sources.</p></div>
        <div className="feed-live-indicator"><i /> Auto-refreshes every 60 seconds</div>
      </div>

      <section className="panel detections-filter-panel" aria-label="Detection filters">
        <label>Source<select value={filters.source} onChange={(event) => setFilters((value) => ({ ...value, source: event.target.value }))}><option value="">All sources</option>{sources.map((source) => <option key={source} value={source}>{sourceLabel(source)}</option>)}</select></label>
        <label>Status<select value={filters.status} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}><option value="">All statuses</option>{STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}</select></label>
        <label>From date<input type="date" value={filters.date_from} onChange={(event) => setFilters((value) => ({ ...value, date_from: event.target.value }))} /></label>
        <label>To date<input type="date" value={filters.date_to} onChange={(event) => setFilters((value) => ({ ...value, date_to: event.target.value }))} /></label>
        <button className="clear-detection-filters" onClick={() => setFilters({ source: "", status: "", date_from: "", date_to: "" })}>Clear</button>
      </section>

      {error && <div className="data-error" role="alert">{error}</div>}
      {statusError && <div className="data-error" role="alert">{statusError}</div>}
      <section className="panel detections-feed-panel">
        <div className="panel-heading"><div><h2>Recent detections</h2><p>Most recent events first · showing up to 50 matching rows</p></div><span className="recent-count">{rows.length} rows</span></div>
        <div className="table-scroll">
          <table className="detection-table fire-detections-table">
            <thead><tr><th>Cell</th><th>Source</th><th>Signals</th><th>Confidence</th><th>Detected</th><th>Status</th><th>Review</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan="7" className="prediction-empty">Loading detection records…</td></tr> : rows.length ? rows.map((row) => <tr key={row.id} tabIndex={row.cell_id ? 0 : -1} className={row.cell_id ? "detection-clickable-row" : ""} onClick={() => openCell(row)} onKeyDown={(event) => { if ((event.key === "Enter" || event.key === " ") && row.cell_id) { event.preventDefault(); openCell(row); } }}>
                <td className="cell-id">{row.cell_id || "Unassigned"}{row.center_lat != null && <small>{Number(row.center_lat).toFixed(4)}, {Number(row.center_lng).toFixed(4)}</small>}</td>
                <td><span className={`detection-source-badge ${row.source === "test_dataset" ? "source-test-dataset" : "source-live"}`}>{sourceLabel(row.source)}</span>{row.source === "test_dataset" && <small className="test-data-tag">TEST DATA</small>}</td>
                <td><div className="detection-signal-list"><span className={row.fire_detected ? "status-fire" : "status-clear"}>{row.fire_detected ? "Fire" : "No fire"}</span><span className={row.smoke_detected ? "status-smoke" : "status-clear"}>{row.smoke_detected ? "Smoke" : "No smoke"}</span></div></td>
                <td>{confidenceLabel(row.confidence)}</td>
                <td className="detected-time">{formatTimestamp(row.detected_at)}</td>
                <td><span className={`detection-status-badge status-${row.status || "unverified"}`}>{STATUS_LABELS[row.status] || "Unverified"}</span></td>
                <td onClick={(event) => event.stopPropagation()}><select aria-label={`Review status for ${row.cell_id || row.id}`} disabled={updatingId === row.id} value={row.status || "unverified"} onChange={(event) => updateStatus(row, event.target.value)}>{STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}</select></td>
              </tr>) : <tr><td colSpan="7" className="prediction-empty">No detections match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="detections-feed-footer">{rows.length ? `Latest matching event: ${formatTimestamp(rows[0].detected_at)}` : "No matching detection records"}<button onClick={() => loadRows(true)}>Refresh now</button></div>
      </section>
    </section>
  );
}
