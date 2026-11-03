import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCachedValue, getDashboardSummary } from "../api/client";

const RISK_TIERS = [
  { key: "low", label: "Low risk", color: "#16a36a", icon: "↓" },
  { key: "moderate", label: "Moderate risk", color: "#d6a51d", icon: "−" },
  { key: "high", label: "High risk", color: "#ea7929", icon: "↑" },
  { key: "extreme", label: "Extreme risk", color: "#dc4b42", icon: "!" },
];

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function isRecentlyUpdated(value, now) {
  if (!value) return false;
  const elapsed = now - new Date(value).getTime();
  return Number.isFinite(elapsed) && elapsed >= 0 && elapsed <= 35 * 60 * 1000;
}

function RiskDonut({ distribution }) {
  const total = RISK_TIERS.reduce((sum, tier) => sum + (distribution?.[tier.key] ?? 0), 0);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="donut-wrap">
      <svg className="risk-donut" viewBox="0 0 160 160" role="img" aria-label={`Risk distribution across ${total} predictions`}>
        <circle cx="80" cy="80" r={radius} fill="none" stroke="#e8eee8" strokeWidth="18" />
        {total > 0 && RISK_TIERS.map((tier) => {
          const value = distribution?.[tier.key] ?? 0;
          const length = (value / total) * circumference;
          const segmentOffset = offset;
          offset += length;
          if (value === 0) return null;
          return (
            <circle
              key={tier.key}
              cx="80"
              cy="80"
              r={radius}
              fill="none"
              stroke={tier.color}
              strokeWidth="18"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={-segmentOffset}
              transform="rotate(-90 80 80)"
            />
          );
        })}
        <text x="80" y="77" textAnchor="middle" className="donut-total">{total}</text>
        <text x="80" y="96" textAnchor="middle" className="donut-caption">cells</text>
      </svg>
      {total === 0 && <p className="donut-empty">No data yet</p>}
    </div>
  );
}

function MetricCard({ label, value, icon, color, className = "", onClick, footnote = "Latest cell state" }) {
  const [displayCount, setDisplayCount] = useState(0);

  useEffect(() => {
    if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setDisplayCount(value);
      return undefined;
    }

    let frameId;
    let startTime;
    const duration = 600;
    const animate = (timestamp) => {
      if (startTime === undefined) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      setDisplayCount(Math.round(value * eased));
      if (progress < 1) frameId = window.requestAnimationFrame(animate);
    };

    setDisplayCount(0);
    frameId = window.requestAnimationFrame(animate);
    return () => window.cancelAnimationFrame(frameId);
  }, [value]);

  const shownValue = typeof value === "number" ? displayCount : value;

  const CardElement = onClick ? "button" : "article";
  return (
    <CardElement className={`metric-card ${onClick ? "metric-card-button" : ""} ${className}`} style={{ "--metric-accent": color }} onClick={onClick} type={onClick ? "button" : undefined}>
      <div className="metric-card-top">
        <span className="metric-label">{label}</span>
        <span className="metric-icon" aria-hidden="true">{icon}</span>
      </div>
      <div className="metric-value" aria-label={`${label}: ${value}`}>{shownValue}</div>
      <div className="metric-footnote">{footnote}</div>
    </CardElement>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(() => getCachedValue("dashboard-summary") ?? null);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      getDashboardSummary()
        .then((data) => {
          if (!cancelled) {
            setSummary(data);
            setError(false);
          }
        })
        .catch(() => {
          if (!cancelled) setError(true);
        });
    };
    refresh();
    const refreshId = window.setInterval(refresh, 60_000);
    const clockId = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(refreshId);
      window.clearInterval(clockId);
    };
  }, []);

  const distribution = summary?.risk_distribution;
  const detections = summary?.recent_detections ?? [];
  const recentlyUpdated = isRecentlyUpdated(summary?.latest_prediction_at, now);

  return (
    <div className="dashboard-page">
      <div className="dashboard-intro">
        <div>
          <h2>Operational overview</h2>
          <p>Current fire activity and risk distribution across monitored grid cells.</p>
        </div>
        <div className="dashboard-statuses">
          <div className={`dashboard-status updated-status ${recentlyUpdated ? "is-current" : "is-stale"}`}>
            <span className="status-dot" />
            <span><strong>Last updated</strong><small>{formatTimestamp(summary?.latest_prediction_at)}</small></span>
          </div>
          <div className={`dashboard-status scheduler-status ${summary?.scheduler_active ? "is-current" : "is-stale"}`}>
            <span className="status-dot" />
            <span><strong>{summary?.scheduler_active ? "Auto-update active" : "Scheduler inactive"}</strong><small>{summary ? `Every ${summary.update_interval_minutes} min` : "Checking scheduler…"}</small></span>
          </div>
        </div>
      </div>

      {error && <div className="data-error" role="alert">Dashboard data is unavailable. Check the backend connection and reload this page.</div>}

      <section className="metric-grid" aria-label="Live metrics">
        <MetricCard label="Active fires" value={summary ? summary.active_fires : "—"} icon="♨" color="#db5143" className="fire-metric" footnote="Latest detection per cell" />
        {RISK_TIERS.map((tier) => (
          <MetricCard
            key={tier.key}
            label={tier.label}
            value={summary ? distribution?.[tier.key] ?? 0 : "—"}
            icon={tier.icon}
            color={tier.color}
            footnote="Latest prediction per cell"
            onClick={tier.key === "extreme" ? () => navigate("/live-map", { state: { focusExtreme: true } }) : undefined}
          />
        ))}
      </section>

      <div className="dashboard-secondary-stats">
        <span><strong>{summary ? summary.cumulative_predictions.toLocaleString() : "—"}</strong> cumulative prediction history</span>
        <span>{summary ? `${summary.cells_with_prediction} of ${summary.grid_cells_total} cells have a prediction` : "Cell coverage loading…"}</span>
      </div>

      <section className="dashboard-panels">
        <article className="panel risk-panel">
          <div className="panel-heading">
            <div><h2>Risk distribution</h2><p>Most recent prediction per cell</p></div>
          </div>
          {summary ? (
            <div className="risk-panel-content">
              <RiskDonut distribution={distribution} />
              <div className="risk-legend">
                {RISK_TIERS.map((tier) => (
                  <div className="risk-legend-row" key={tier.key}>
                    <span className="legend-label"><i style={{ backgroundColor: tier.color }} />{tier.label}</span>
                    <strong>{distribution?.[tier.key] ?? 0}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : <div className="panel-empty">{error ? "Unable to load risk data." : "Loading risk data…"}</div>}
        </article>

        <article className="panel detections-panel">
          <div className="panel-heading">
            <div><h2>Recent detections</h2><p>Latest recorded sensor events</p></div>
            <span className="recent-count">{summary ? `${detections.length} records` : "—"}</span>
          </div>
          {!summary ? (
            <div className="panel-empty">{error ? "Unable to load detections." : "Loading detections…"}</div>
          ) : detections.length === 0 ? (
            <div className="panel-empty">No data yet</div>
          ) : (
            <div className="table-scroll">
              <table className="detection-table">
                <thead><tr><th>Grid cell</th><th>Fire</th><th>Smoke</th><th>Confidence</th><th>Detected</th></tr></thead>
                <tbody>
                  {detections.map((row) => (
                    <tr key={row.id}>
                      <td className="cell-id">{row.cell_id ?? "—"}</td>
                      <td><span className={`status-pill ${row.fire_detected ? "status-fire" : "status-clear"}`}>{row.fire_detected ? "Detected" : "No fire"}</span></td>
                      <td><span className={`status-pill ${row.smoke_detected ? "status-smoke" : "status-clear"}`}>{row.smoke_detected ? "Detected" : "No smoke"}</span></td>
                      <td>{Number.isFinite(Number(row.confidence)) ? `${(Number(row.confidence) * 100).toFixed(0)}%` : "—"}</td>
                      <td className="detected-time">{formatTimestamp(row.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>
      <p className="dashboard-footnote">Figures reflect database records and may include repeated predictions or detection events.</p>
    </div>
  );
}
