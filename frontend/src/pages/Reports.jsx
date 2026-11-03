import { useEffect, useMemo, useState } from "react";
import { getReportEvaluation, getReportSnapshot, getReportTrend } from "../api/client";

const RISK_TIERS = [
  { key: "low", label: "Low", color: "#218354" },
  { key: "moderate", label: "Moderate", color: "#b68c16" },
  { key: "high", label: "High", color: "#d56b29" },
  { key: "extreme", label: "Extreme", color: "#c9433a" },
];
const SOURCE_LABELS = { nasa_firms: "NASA FIRMS", test_dataset: "Test dataset", yolo_upload: "YOLO upload", yolo: "YOLO upload", satellite: "Satellite", aerial: "Aerial", drone: "Drone", webcam: "Webcam" };
const labelSource = (value) => SOURCE_LABELS[value] || String(value || "Unknown").replaceAll("_", " ");
const formatDateTime = (value) => value ? new Date(value).toLocaleString() : "Not recorded";
const display = (value, digits = 2) => value == null || value === "" || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);

function TrendChart({ points }) {
  const valid = points.filter((point) => point.average_fwi != null);
  if (!valid.length) return <div className="report-empty">No FWI predictions recorded in this date range. The requested days are shown as gaps below.</div>;
  const width = 900;
  const height = 220;
  const pad = { left: 42, right: 12, top: 16, bottom: 33 };
  const values = valid.map((point) => point.average_fwi);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const xAt = (index) => pad.left + (points.length <= 1 ? 0 : index / (points.length - 1) * (width - pad.left - pad.right));
  const yAt = (value) => height - pad.bottom - ((value - min) / span) * (height - pad.top - pad.bottom);
  const segments = [];
  let current = [];
  points.forEach((point, index) => {
    if (point.average_fwi == null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push(`${xAt(index)},${yAt(point.average_fwi)}`);
  });
  if (current.length) segments.push(current);

  return <div className="report-chart-wrap"><svg className="report-trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily average FWI trend; missing prediction days are gaps">
    {[0, .5, 1].map((fraction) => { const y = pad.top + fraction * (height - pad.top - pad.bottom); return <g key={fraction}><line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="report-chart-gridline"/><text x={pad.left - 8} y={y + 4} textAnchor="end" className="report-chart-label">{display(max - fraction * span, 1)}</text></g>; })}
    {segments.map((segment, index) => segment.length > 1 && <polyline key={index} points={segment.join(" ")} className="report-chart-line" />)}
    {points.map((point, index) => point.average_fwi != null && <circle key={point.date} cx={xAt(index)} cy={yAt(point.average_fwi)} r="3.5" className="report-chart-point"><title>{`${point.date}: average FWI ${display(point.average_fwi, 4)}`}</title></circle>)}
    <text x={pad.left} y={height - 8} className="report-chart-label">{points[0]?.date}</text>
    <text x={width - pad.right} y={height - 8} textAnchor="end" className="report-chart-label">{points.at(-1)?.date}</text>
  </svg><div className="report-chart-legend"><span><i /> Daily average FWI</span><small>Line gaps indicate days with no prediction rows.</small></div></div>;
}

function snapshotCsvRows(snapshot) {
  const rows = [["section", "metric", "value"]];
  const add = (section, metric, value) => rows.push([section, metric, value ?? ""]);
  add("report", "generated_at", snapshot.generated_at);
  const grid = snapshot.grid || {};
  add("grid", "total_cells", grid.total_cells);
  add("grid", "cells_with_latest_prediction", grid.cells_with_latest_prediction);
  Object.entries(grid.risk_level_breakdown || {}).forEach(([key, value]) => add("risk_breakdown", key, value));
  const top = grid.highest_risk_cell;
  add("highest_risk_cell", "cell_id", top?.cell_id);
  add("highest_risk_cell", "fwi", top?.fwi);
  add("highest_risk_cell", "risk_level", top?.risk_level);
  add("highest_risk_cell", "predicted_at", top?.predicted_at);
  Object.entries(snapshot.forest_vulnerability || {}).forEach(([key, value]) => {
    if (value == null || typeof value !== "object") add("forest_vulnerability", key, value);
    else Object.entries(value).forEach(([component, componentValue]) => add(`forest_vulnerability.${key}`, component, componentValue));
  });
  add("detections", "total", snapshot.detections?.total);
  add("detections", "status_column_available", snapshot.detections?.status_column_available);
  Object.entries(snapshot.detections?.by_source || {}).forEach(([key, value]) => add("detections_by_source", key, value));
  if (snapshot.detections?.status_column_available) Object.entries(snapshot.detections?.by_status || {}).forEach(([key, value]) => add("detections_by_status", key, value));
  else add("detections_by_status", "status_column_available", false);
  Object.entries(snapshot.scheduler || {}).forEach(([key, value]) => add("scheduler", key, value));
  return rows;
}

function downloadCsv(filename, rows) {
  const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function Reports() {
  const [reportType, setReportType] = useState("snapshot");
  const [days, setDays] = useState(14);
  const [snapshot, setSnapshot] = useState(null);
  const [trend, setTrend] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const request = reportType === "snapshot" ? getReportSnapshot() : reportType === "trend" ? getReportTrend(days) : getReportEvaluation();
    request.then((data) => {
      if (!active) return;
      if (reportType === "snapshot") setSnapshot(data);
      else if (reportType === "trend") setTrend(data);
      else setEvaluation(data);
    }).catch((err) => active && setError(err.response?.data?.detail || err.message || "Unable to load report data."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [reportType, days]);

  const csvRows = useMemo(() => {
    if (reportType === "snapshot") return snapshot ? snapshotCsvRows(snapshot) : [];
    if (reportType === "trend") return [["date", "average_fwi", "cells_with_prediction", "detection_count", "has_prediction_data", "has_detection_data"], ...(trend?.points || []).map((point) => [point.date, point.average_fwi ?? "", point.cells_with_prediction, point.detection_count, point.has_prediction_data, point.has_detection_data])];
    const rows = [["section", "metric", "value", "run", "image", "ground_truth", "predicted", "latency_ms", "confidence", "fire_detected", "smoke_detected"]];
    const execution = evaluation?.execution;
    const accuracy = evaluation?.accuracy;
    if (execution) {
      ["generated_at", "device", "platform", "python_version", "model_path", "image_count", "images", "warmup_runs", "iterations_per_image", "measured_inferences", "cold_start_first_inference_ms", "throughput_images_per_second"].forEach((key) => rows.push(["runtime_summary", key, Array.isArray(execution[key]) ? execution[key].join("; ") : execution[key] ?? ""]));
      Object.entries(execution.warm_latency_ms || {}).forEach(([key, value]) => rows.push(["warm_latency_ms", key, value]));
      (execution.runs || []).forEach((run) => rows.push(["runtime_sample", "", "", run.run, run.image, "", "", run.latency_ms, run.confidence, run.fire_detected, run.smoke_detected]));
    }
    if (accuracy) {
      ["generated_at", "dataset", "split", "sample_size", "sample_per_category", "metric_scope", "overall_image_category_accuracy", "overall_correct", "overall_total"].forEach((key) => rows.push(["accuracy_summary", key, accuracy[key] ?? ""]));
      ["fire_binary_metrics", "smoke_binary_metrics"].forEach((key) => Object.entries(accuracy[key] || {}).forEach(([metric, value]) => rows.push([key, metric, value ?? ""])));
      (accuracy.images || []).forEach((item) => rows.push(["accuracy_sample", "", "", "", item.image_id, item.ground_truth, item.predicted, item.inference_ms, item.confidence, item.fire_detected, item.smoke_detected]));
      Object.entries(accuracy.confusion_matrix || {}).forEach(([truth, predictions]) => Object.entries(predictions).forEach(([predicted, count]) => rows.push(["confusion_matrix", `${truth} -> ${predicted}`, count])));
    }
    return rows.length > 1 ? rows : [];
  }, [reportType, snapshot, trend, evaluation]);

  const exportCsv = () => {
    if (csvRows.length) downloadCsv(`firegridnet-${reportType}-${new Date().toISOString().slice(0, 10)}.csv`, csvRows);
  };
  const currentGrid = snapshot?.grid;
  const vulnerability = snapshot?.forest_vulnerability;
  const detections = snapshot?.detections;
  const scheduler = snapshot?.scheduler;
  const execution = evaluation?.execution;
  const accuracy = evaluation?.accuracy;

  return <section className="reports-page">
    <div className="reports-heading"><div><h2>Reporting</h2><p>Exportable operational and historical summaries from recorded system data.</p></div><div className="reports-actions"><button onClick={() => window.print()}>Download PDF</button><button className="report-csv-button" onClick={exportCsv} disabled={!csvRows.length}>Download CSV</button></div></div>
    <div className="report-switcher"><button className={reportType === "snapshot" ? "active" : ""} onClick={() => setReportType("snapshot")}>Operational snapshot</button><button className={reportType === "trend" ? "active" : ""} onClick={() => setReportType("trend")}>Historical trend</button><button className={reportType === "execution" ? "active" : ""} onClick={() => setReportType("execution")}>Execution evaluation</button>{reportType === "trend" && <label>Period<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>Last 7 days</option><option value={14}>Last 14 days</option><option value={30}>Last 30 days</option></select></label>}</div>
    {error && <div className="data-error" role="alert">{error}</div>}
    {loading && <div className="report-loading">Loading report data…</div>}

    <article className="report-document" aria-busy={loading}>
      {reportType === "snapshot" ? <>
        <header className="report-document-header"><div><span className="prediction-eyebrow">FIREGRIDNET · OPERATIONS REPORT</span><h2>Operational snapshot</h2><p>Point-in-time summary of the monitored grid and its latest recorded conditions.</p></div><div className="report-timestamp"><span>Generated</span><strong>{formatDateTime(snapshot?.generated_at)}</strong></div></header>
        <section className="report-summary-cards">
          <div><span>Total grid cells</span><strong>{currentGrid?.total_cells ?? "—"}</strong><small>{currentGrid ? `${currentGrid.cells_with_latest_prediction} with a current prediction` : "Awaiting report data"}</small></div>
          <div><span>Total detections</span><strong>{detections?.total ?? "—"}</strong><small>All recorded sources</small></div>
          <div className="report-top-cell"><span>Highest-risk cell</span><strong>{currentGrid?.highest_risk_cell?.cell_id || "No prediction"}</strong><small>{currentGrid?.highest_risk_cell ? `FWI ${display(currentGrid.highest_risk_cell.fwi, 2)} · ${currentGrid.highest_risk_cell.risk_level}` : "No latest risk row"}</small></div>
        </section>
        <div className="report-content-grid">
          <section className="report-section"><h3>Current risk distribution</h3><div className="report-risk-list">{RISK_TIERS.map((tier) => <div key={tier.key}><span><i style={{ background: tier.color }} />{tier.label}</span><strong>{currentGrid?.risk_level_breakdown?.[tier.key] ?? "—"}</strong></div>)}</div><small className="report-section-note">Counts use each cell’s most recent prediction.</small></section>
          <section className="report-section"><h3>Forest-wide vulnerability</h3><div className="report-vulnerability-highlight"><strong>{vulnerability?.high_extreme_percent == null ? "—" : `${display(vulnerability.high_extreme_percent, 1)}%`}</strong><span>cells currently High / Extreme</span></div><div className="report-inline-metrics"><div><span>Average FWI</span><strong>{display(vulnerability?.average_fwi)}</strong></div><div><span>Three-day trend</span><strong className={`trend-${vulnerability?.trend || "unavailable"}`}>{vulnerability?.trend || "Unavailable"}</strong></div></div>{vulnerability?.trend === "unavailable" && <small className="report-section-note">No comparable three-day average is currently recorded.</small>}</section>
          <section className="report-section"><h3>Detections by source</h3>{Object.entries(detections?.by_source || {}).length ? <div className="report-risk-list">{Object.entries(detections.by_source).map(([source, count]) => <div key={source}><span>{labelSource(source)}</span><strong>{count}</strong></div>)}</div> : <p className="report-muted">No detections recorded.</p>}</section>
          <section className="report-section"><h3>Detection review status</h3>{detections?.status_column_available ? Object.entries(detections.by_status || {}).length ? <div className="report-risk-list">{Object.entries(detections.by_status).map(([status, count]) => <div key={status}><span>{status.replaceAll("_", " ")}</span><strong>{count}</strong></div>)}</div> : <p className="report-muted">No status counts recorded.</p> : <p className="report-migration-note">Status counts unavailable: the `detections.status` migration has not been applied.</p>}</section>
          <section className="report-section report-scheduler-section"><h3>Scheduler</h3><div className="scheduler-report-state"><i className={scheduler?.active ? "is-active" : ""} /><strong>{scheduler?.active ? "Active" : "Inactive"}</strong><span>{scheduler?.interval_minutes ? `Every ${scheduler.interval_minutes} minutes` : "Interval unavailable"}</span></div><div className="report-inline-metrics"><div><span>Last run</span><strong>{formatDateTime(scheduler?.last_run_at)}</strong></div><div><span>Next scheduled run</span><strong>{formatDateTime(scheduler?.next_run_at)}</strong></div></div></section>
        </div>
      </> : reportType === "trend" ? <>
        <header className="report-document-header"><div><span className="prediction-eyebrow">FIREGRIDNET · HISTORICAL REPORT</span><h2>Daily risk and detection trend</h2><p>Daily mean FWI uses the latest available prediction per cell for that UTC date.</p></div><div className="report-timestamp"><span>Range</span><strong>Last {trend?.days ?? days} days · UTC</strong></div></header>
        <section className="report-section trend-report-section"><h3>Average FWI over time</h3><TrendChart points={trend?.points || []} /></section>
        <section className="report-section trend-report-section"><h3>Daily source records</h3><div className="table-scroll"><table className="detection-table report-trend-table"><thead><tr><th>Date (UTC)</th><th>Daily average FWI</th><th>Cells represented</th><th>Detection count</th><th>Record coverage</th></tr></thead><tbody>{trend?.points?.length ? trend.points.map((point) => <tr key={point.date}><td>{point.date}</td><td>{point.average_fwi == null ? "No prediction data" : display(point.average_fwi, 4)}</td><td>{point.cells_with_prediction}</td><td>{point.detection_count}</td><td>{point.has_prediction_data ? "Predictions recorded" : point.has_detection_data ? "Detections only" : "No records"}</td></tr>) : <tr><td colSpan="5" className="report-muted">No trend data available.</td></tr>}</tbody></table></div></section>
      </> : <>
        <header className="report-document-header"><div><span className="prediction-eyebrow">FIREGRIDNET · MODEL EVALUATION</span><h2>Execution performance and sample accuracy</h2><p>Runtime measurements and a separate image-level check from the D-Fire test split.</p></div><div className="report-timestamp"><span>Latest benchmark</span><strong>{formatDateTime(execution?.generated_at || accuracy?.generated_at)}</strong></div></header>
        <section className="report-section evaluation-runtime-section"><h3>YOLO inference runtime</h3>{execution ? <>
          <div className="report-summary-cards evaluation-metrics"><div><span>Cold start + first inference</span><strong>{display(execution.cold_start_first_inference_ms, 1)} ms</strong><small>Model initialization plus first sample</small></div><div><span>Warm median</span><strong>{display(execution.warm_latency_ms?.median, 1)} ms</strong><small>{execution.measured_inferences} measured inferences</small></div><div><span>Warm p95</span><strong>{display(execution.warm_latency_ms?.p95, 1)} ms</strong><small>95th percentile latency</small></div><div><span>Throughput</span><strong>{display(execution.throughput_images_per_second, 2)}</strong><small>images / second</small></div></div>
          <p className="report-section-note">{execution.scope}. Device: {execution.device}. Generated {formatDateTime(execution.generated_at)}.</p>
          <div className="table-scroll"><table className="detection-table report-trend-table"><thead><tr><th>Run</th><th>Image</th><th>Latency (ms)</th><th>Confidence</th><th>Fire</th><th>Smoke</th></tr></thead><tbody>{(execution.runs || []).slice(0, 20).map((run, index) => <tr key={`${run.run}-${run.image}-${index}`}><td>{run.run}</td><td>{run.image}</td><td>{display(run.latency_ms, 3)}</td><td>{display(run.confidence, 4)}</td><td>{run.fire_detected ? "Yes" : "No"}</td><td>{run.smoke_detected ? "Yes" : "No"}</td></tr>)}</tbody></table></div>
        </> : <div className="report-empty">No execution benchmark has been generated yet. From the backend folder, run <code>python scripts/evaluate_execution.py</code>. It writes JSON and CSV reports under <code>backend/reports/</code>.</div>}</section>
        <section className="report-section evaluation-accuracy-section"><h3>Image-level D-Fire sample evaluation</h3>{accuracy ? <>
          <div className="evaluation-accuracy-summary"><strong>{accuracy.overall_image_category_accuracy == null ? "—" : `${display(accuracy.overall_image_category_accuracy * 100, 1)}%`}</strong><span>exact category accuracy · {accuracy.overall_correct} / {accuracy.overall_total} images</span><small>{accuracy.metric_scope} Sample size: {accuracy.sample_size}; {accuracy.sample_per_category} images per category. This is a sample evaluation, not a full-dataset result.</small></div>
          <div className="report-content-grid evaluation-class-metrics">{[["Fire", accuracy.fire_binary_metrics], ["Smoke", accuracy.smoke_binary_metrics]].map(([label, metrics]) => <div className="report-section" key={label}><h3>{label} · one-vs-rest</h3><div className="report-inline-metrics"><div><span>Precision</span><strong>{metrics?.precision == null ? "—" : `${display(metrics.precision * 100, 1)}%`}</strong></div><div><span>Recall</span><strong>{metrics?.recall == null ? "—" : `${display(metrics.recall * 100, 1)}%`}</strong></div><div><span>F1</span><strong>{metrics?.f1 == null ? "—" : `${display(metrics.f1 * 100, 1)}%`}</strong></div><div><span>TP / FP / FN / TN</span><strong>{[metrics?.tp, metrics?.fp, metrics?.fn, metrics?.tn].join(" / ")}</strong></div></div></div>)}</div>
          <div className="table-scroll"><table className="detection-table report-trend-table"><thead><tr><th>Dataset image</th><th>Ground truth</th><th>Predicted</th><th>Confidence</th><th>Latency (ms)</th></tr></thead><tbody>{(accuracy.images || []).slice(0, 24).map((item) => <tr key={item.image_id}><td>{item.image_id}</td><td>{item.ground_truth}</td><td>{item.predicted}</td><td>{display(item.confidence, 4)}</td><td>{display(item.inference_ms, 3)}</td></tr>)}</tbody></table></div>
        </> : <div className="report-empty">No D-Fire sample evaluation has been generated yet. From the backend folder, run <code>python scripts/evaluate_dfire_sample.py</code>. This reports image-level fire/smoke metrics; it does not compute localization mAP.</div>}</section>
      </>}
      <footer className="report-document-footer">FireGridNet · Values are drawn from stored grid, risk, detection, and scheduler records.</footer>
    </article>
  </section>;
}
