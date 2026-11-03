import { useEffect, useState } from "react";
import { getCellDetails } from "../api/client";

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "—";
}

export default function CellDetailPanel({ cellId, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!cellId) {
      setDetails(null);
      setLoading(false);
      setError(false);
      return undefined;
    }

    setLoading(true);
    setError(false);
    getCellDetails(cellId)
      .then((data) => {
        if (!cancelled) setDetails(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [cellId]);

  if (!cellId) {
    return (
      <aside className="cell-detail-panel cell-detail-empty">
        <div className="cell-detail-empty-mark" aria-hidden="true">⌖</div>
        <h2>Select a cell</h2>
        <p>Choose a grid cell on the map to inspect its current risk, weather, and history.</p>
      </aside>
    );
  }

  if (loading && !details) {
    return <aside className="cell-detail-panel"><h2>{cellId}</h2><p className="cell-detail-message">Loading cell records…</p></aside>;
  }

  if (error && !details) {
    return <aside className="cell-detail-panel"><h2>{cellId}</h2><p className="cell-detail-error">Cell data is unavailable. Check the backend and try selecting the cell again.</p></aside>;
  }

  const currentRisk = details?.current_risk;
  const weather = currentRisk?.features_used;
  const detection = details?.latest_detection;
  const vulnerability = details?.vulnerability;
  const components = vulnerability?.components;
  const riskLevel = currentRisk?.risk_level ?? "no data";

  return (
    <aside className="cell-detail-panel" aria-label={`Details for ${cellId}`}>
      <div className="cell-detail-heading">
        <div><span className="cell-detail-eyebrow">SELECTED GRID CELL</span><h2>{cellId}</h2></div>
        <button type="button" className="cell-detail-close" onClick={onClose} aria-label="Close cell details">×</button>
      </div>

      <section className="cell-detail-section current-risk-section">
        <div className="cell-risk-topline"><span>Current risk</span><time>{formatTimestamp(currentRisk?.predicted_at)}</time></div>
        <div className="cell-risk-value"><strong className={`risk-tier-${riskLevel}`}>{currentRisk ? riskLevel : "No prediction"}</strong><b>{currentRisk ? formatNumber(currentRisk.risk_score) : "—"}<small> FWI</small></b></div>
        {weather ? (
          <div className="weather-grid">
            <div><span>Temperature</span><strong>{formatNumber(weather.temperature_c)} °C</strong></div>
            <div><span>Humidity</span><strong>{formatNumber(weather.humidity_pct, 0)}%</strong></div>
            <div><span>Wind</span><strong>{formatNumber(weather.wind_speed_kmh)} km/h</strong></div>
            <div><span>Rainfall</span><strong>{formatNumber(weather.rainfall_mm)} mm</strong></div>
          </div>
        ) : <p className="cell-detail-muted">Weather inputs unavailable.</p>}
      </section>

      <section className="cell-detail-section vulnerability-section">
        <div className="cell-section-heading"><h3>Vulnerability</h3><span>0–100</span></div>
        <div className="vulnerability-score"><strong>{formatNumber(vulnerability?.score, 2)}</strong><span>Composite score</span></div>
        <dl className="vulnerability-components">
          <div><dt>High / Extreme history</dt><dd>{formatNumber(components?.pct_high_extreme, 1)}%</dd></div>
          <div><dt>Recent weighted average FWI</dt><dd>{formatNumber(components?.avg_fwi_recent)}</dd></div>
          <div><dt>Fire / smoke detections</dt><dd>{components?.detection_frequency ?? "—"}</dd></div>
        </dl>
        <p className="vulnerability-footnote">Weighted: 50% risk history, 30% recent FWI, 20% detections.</p>
      </section>

      <section className="cell-detail-section detection-section">
        <div className="cell-section-heading"><h3>Latest detection</h3></div>
        {detection ? (
          <div className="latest-detection">
            <span className={`status-pill ${detection.fire_detected || detection.smoke_detected ? "status-fire" : "status-clear"}`}>
              {detection.fire_detected ? "Fire" : detection.smoke_detected ? "Smoke" : "No fire / smoke"}
            </span>
            <span>{detection.source}</span>
            <span>{formatTimestamp(detection.detected_at)}</span>
          </div>
        ) : <p className="cell-detail-muted">No detection recorded for this cell.</p>}
      </section>

      <section className="cell-detail-section history-section">
        <div className="cell-section-heading"><h3>Prediction history</h3><span>Last {details?.history?.length ?? 0}</span></div>
        {!details?.history?.length ? <p className="cell-detail-muted">No risk predictions yet.</p> : (
          <div className="cell-history-scroll">
            <table className="cell-history-table">
              <thead><tr><th>Date</th><th>FWI</th><th>Risk</th></tr></thead>
              <tbody>
                {details.history.map((row) => (
                  <tr key={`${row.predicted_at}-${row.risk_score}`}>
                    <td>{formatTimestamp(row.predicted_at)}</td>
                    <td>{formatNumber(row.risk_score)}</td>
                    <td><span className={`history-tier risk-tier-${row.risk_level}`}>{row.risk_level}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </aside>
  );
}
