import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getCellDetails,
  getCellForecast,
  getCellRiskHistory,
  getForestVulnerability,
  getGridCells,
  getNeighborExposure,
  getRecentPredictions,
  getRegionalRiskScore,
} from "../api/client";

const ZONES = ["Northwest block", "Northeast block", "Southwest block", "Southeast block"];
const zoneForCell = (cellId) => {
  const match = cellId?.match(/MNR-(\d+)-(\d+)/);
  if (!match) return "Other";
  const row = Number(match[1]);
  const column = Number(match[2]);
  return `${row < 8 ? "North" : "South"}${column < 7 ? "west" : "east"} block`;
};
const tierClass = (tier) => `risk-tier-${String(tier || "").toLowerCase()}`;
const fmt = (value, digits = 1) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
const dateTime = (value) => value ? new Date(value).toLocaleString() : "—";

function TrendChart({ rows }) {
  if (!rows?.length) return <div className="prediction-empty">No prediction history in this period.</div>;
  const width = 720;
  const height = 230;
  const pad = { left: 42, right: 14, top: 16, bottom: 34 };
  const values = rows.map((row) => Number(row.risk_score));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = pad.left + (rows.length === 1 ? (width - pad.left - pad.right) / 2 : index / (rows.length - 1) * (width - pad.left - pad.right));
    const y = height - pad.bottom - ((value - min) / span) * (height - pad.top - pad.bottom);
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="prediction-chart-wrap">
      <svg className="prediction-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`FWI trend with ${rows.length} prediction points`}>
        {[0, 0.5, 1].map((fraction) => {
          const y = pad.top + fraction * (height - pad.top - pad.bottom);
          const label = (max - fraction * span).toFixed(1);
          return <g key={fraction}><line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="prediction-gridline"/><text x={pad.left - 8} y={y + 4} textAnchor="end" className="prediction-axis-label">{label}</text></g>;
        })}
        <polyline points={points} className="prediction-line" />
        {rows.map((row, index) => {
          const [cx, cy] = points.split(" ")[index].split(",");
          return <circle key={`${row.predicted_at}-${index}`} cx={cx} cy={cy} r="3.5" className="prediction-point"><title>{`${dateTime(row.predicted_at)} · FWI ${fmt(row.risk_score, 2)}`}</title></circle>;
        })}
        <text x={pad.left} y={height - 8} className="prediction-axis-label">{new Date(rows[0].predicted_at).toLocaleDateString()}</text>
        <text x={width - pad.right} y={height - 8} textAnchor="end" className="prediction-axis-label">{new Date(rows.at(-1).predicted_at).toLocaleDateString()}</text>
      </svg>
      <div className="prediction-chart-caption">Fire Weather Index · {rows.length} real prediction{rows.length === 1 ? "" : "s"}</div>
    </div>
  );
}

export default function RiskPrediction() {
  const navigate = useNavigate();
  const [cells, setCells] = useState([]);
  const [selectedCell, setSelectedCell] = useState("");
  const [zone, setZone] = useState("All zones");
  const [regional, setRegional] = useState(null);
  const [forest, setForest] = useState(null);
  const [details, setDetails] = useState(null);
  const [history, setHistory] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [forecastError, setForecastError] = useState("");
  const [exposure, setExposure] = useState(null);
  const [exposureError, setExposureError] = useState("");
  const [log, setLog] = useState({ items: [], total: 0, limit: 25, offset: 0 });
  const [descending, setDescending] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getGridCells(), getRegionalRiskScore(), getForestVulnerability()])
      .then(([cellRows, score, vulnerability]) => {
        if (!active) return;
        setCells(cellRows);
        setSelectedCell((current) => current || score.cell_id || cellRows[0]?.cell_id || "");
        setRegional(score);
        setForest(vulnerability);
      })
      .catch((err) => active && setError(err.response?.data?.detail || err.message || "Unable to load regional risk data."));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    getRecentPredictions({ limit: 25, offset: log.offset, descending })
      .then((data) => active && setLog(data))
      .catch((err) => active && setError(err.response?.data?.detail || err.message || "Unable to load prediction log."));
    return () => { active = false; };
  }, [log.offset, descending]);

  useEffect(() => {
    if (!selectedCell) return undefined;
    let active = true;
    setDetails(null);
    setHistory([]);
    setForecast(null);
    setForecastError("");
    Promise.all([getCellDetails(selectedCell), getCellRiskHistory(selectedCell, 14)])
      .then(([cellDetails, cellHistory]) => {
        if (!active) return;
        setDetails(cellDetails);
        setHistory(cellHistory.history || []);
      })
      .catch((err) => active && setError(err.response?.data?.detail || err.message || "Unable to load selected cell data."));
    getCellForecast(selectedCell)
      .then((result) => active && setForecast(result))
      .catch((err) => active && setForecastError(err.response?.data?.detail || "Seven-day forecast is unavailable."));
    return () => { active = false; };
  }, [selectedCell]);

  useEffect(() => {
    if (!selectedCell || selectedCell !== regional?.cell_id) {
      setExposure(null);
      setExposureError("");
      return undefined;
    }
    let active = true;
    setExposure(null);
    setExposureError("");
    getNeighborExposure(selectedCell)
      .then((result) => active && setExposure(result))
      .catch((err) => active && setExposureError(err.response?.data?.detail || "Neighbor exposure is unavailable."));
    return () => { active = false; };
  }, [selectedCell, regional?.cell_id]);

  const filteredCells = useMemo(() => cells.filter((cell) => zone === "All zones" || zoneForCell(cell.cell_id) === zone), [cells, zone]);
  useEffect(() => {
    if (filteredCells.length && !filteredCells.some((cell) => cell.cell_id === selectedCell)) setSelectedCell(filteredCells[0].cell_id);
  }, [filteredCells, selectedCell]);

  const features = details?.current_risk?.features_used;
  const fwi = details?.fwi_state;
  const hasPrev = log.offset > 0;
  const hasNext = log.offset + log.limit < log.total;

  return (
    <section className="risk-prediction-page">
      {error && <div className="data-error" role="alert">{error}</div>}
      <section className="regional-risk-hero">
        <div><span className="prediction-eyebrow">HIGHEST-RISK CELL</span><h2>Current maximum FWI</h2><p>Highest value across each cell’s latest stored prediction.</p></div>
        <div className="regional-risk-score">
          <strong>{regional?.risk_score == null ? "—" : fmt(regional.risk_score, 1)}</strong>
          <span className={tierClass(regional?.risk_level)}>{regional?.risk_level || "No data yet"}</span>
          <small>{regional?.cell_id || "No cell prediction available"}</small>
        </div>
        <button className="view-risk-cell-button" disabled={!regional?.cell_id} onClick={() => navigate("/live-map", { state: { focusCellId: regional.cell_id } })}>View on map <span aria-hidden="true">↗</span></button>
        <div className="regional-risk-coverage">{regional ? `${regional.cells_with_prediction} of ${regional.total_grid_cells} cells have a prediction` : "Loading actual grid coverage…"}</div>
      </section>

      <section className="forest-vulnerability panel">
        <div className="forest-vulnerability-heading"><span className="prediction-eyebrow">FOREST-WIDE VULNERABILITY</span><h2>Current conditions across the grid</h2></div>
        <div className="forest-vulnerability-metrics">
          <div><span>Cells currently high / extreme</span><strong>{forest?.high_extreme_percent == null ? "—" : `${fmt(forest.high_extreme_percent, 1)}%`}</strong><small>{forest ? `${forest.high_extreme_cells} of ${forest.cells_with_prediction} cells` : "No current prediction data"}</small></div>
          <div><span>Average current FWI</span><strong>{forest?.average_fwi == null ? "—" : fmt(forest.average_fwi, 2)}</strong><small>Across {forest?.cells_with_prediction ?? "—"} cells with latest predictions</small></div>
          <div><span>Three-day average trend</span><strong className={`trend-${forest?.trend || "unavailable"}`}>{forest?.trend || "Unavailable"}</strong><small>{forest?.today_average_fwi == null || forest?.three_days_ago_average_fwi == null ? "No comparable daily averages" : `Today ${fmt(forest.today_average_fwi, 2)} · 3 days ago ${fmt(forest.three_days_ago_average_fwi, 2)}`}</small></div>
        </div>
      </section>

      <div className="prediction-toolbar panel">
        <div><span className="prediction-eyebrow">CELL ANALYSIS</span><h2>Key drivers and forecast</h2></div>
        <div className="prediction-selectors">
          <label>Zone<select value={zone} onChange={(e) => setZone(e.target.value)}><option>All zones</option>{ZONES.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Grid cell<select value={selectedCell} onChange={(e) => setSelectedCell(e.target.value)}>{filteredCells.map((cell) => <option key={cell.cell_id} value={cell.cell_id}>{cell.cell_id}</option>)}</select></label>
        </div>
      </div>

      <div className="prediction-panels">
        <section className="panel prediction-panel">
          <div className="panel-heading"><div><h2>Selected cell conditions</h2><p>{selectedCell || "Select a grid cell"} · latest stored inputs</p></div>{details?.current_risk && <span className={tierClass(details.current_risk.risk_level)}>{details.current_risk.risk_level}</span>}</div>
          <div className="driver-grid">
            <div><span>Temperature</span><strong>{features ? `${fmt(features.temperature_c)} °C` : "No data yet"}</strong></div>
            <div><span>Humidity</span><strong>{features ? `${fmt(features.humidity_pct)} %` : "No data yet"}</strong></div>
            <div><span>Wind</span><strong>{features ? `${fmt(features.wind_speed_kmh)} km/h` : "No data yet"}</strong></div>
            <div><span>Rainfall</span><strong>{features ? `${fmt(features.rainfall_mm)} mm` : "No data yet"}</strong></div>
          </div>
          <div className="fwi-state-row"><div><span>FFMC</span><strong>{fwi ? fmt(fwi.ffmc, 2) : "—"}</strong></div><div><span>DMC</span><strong>{fwi ? fmt(fwi.dmc, 2) : "—"}</strong></div><div><span>DC</span><strong>{fwi ? fmt(fwi.dc, 2) : "—"}</strong></div><small>State date: {fwi?.calculation_date || "No state recorded"}</small></div>
          <div className="cell-score-footer"><span>Latest FWI</span><strong>{details?.current_risk ? fmt(details.current_risk.risk_score, 2) : "No prediction yet"}</strong><time>{dateTime(details?.current_risk?.predicted_at)}</time></div>
        </section>

        <section className="panel prediction-panel">
          <div className="panel-heading"><div><h2>FWI trend</h2><p>Last 14 days for {selectedCell || "selected cell"}</p></div></div>
          <TrendChart rows={history} />
        </section>
      </div>

      {selectedCell === regional?.cell_id && <section className="panel prediction-panel exposure-panel">
        <div className="panel-heading"><div><h2>If this cell ignites, relative exposure of neighboring cells</h2><p>Simplified directional exposure estimate · not a fire-spread simulation or time prediction</p></div>{exposure?.wind_direction_deg != null && <span className="exposure-wind">Wind {fmt(exposure.wind_direction_deg, 0)}°</span>}</div>
        {exposureError ? <div className="prediction-empty">{exposureError}</div> : exposure?.neighbors?.length ? <>
          <div className="exposure-list">{exposure.neighbors.map((neighbor, index) => <div className="exposure-row" key={neighbor.cell_id}>
            <span className="exposure-rank">{index + 1}</span><strong>{neighbor.cell_id}</strong>
            <span className={tierClass(neighbor.risk_level)}>{neighbor.risk_score == null ? "No FWI" : `FWI ${fmt(neighbor.risk_score, 2)}`}</span>
            <span>{neighbor.downwind == null ? "Wind unavailable" : neighbor.downwind ? "Downwind" : "Crosswind / upwind"}</span>
            <b>{neighbor.exposure_score == null ? "—" : fmt(neighbor.exposure_score, 1)}</b>
          </div>)}</div>
          <p className="exposure-formula">{exposure.interpretation} Formula: 50 × downwind indicator + 30 × min(FWI / 20, 1) + 20 × ((100 − humidity) / 100).</p>
        </> : <div className="prediction-empty">Loading current neighbor conditions…</div>}
      </section>}

      <section className="panel prediction-panel forecast-panel">
        <div className="panel-heading"><div><h2>7-day weather forecast</h2><p>{selectedCell ? `OpenWeatherMap · ${selectedCell}` : "Select a cell to load a forecast"}</p></div></div>
        {forecastError ? <div className="prediction-empty">{forecastError}</div> : forecast?.days?.length ? <div className="forecast-days">{forecast.days.map((day) => <article key={day.date}><time>{new Date(day.date * 1000).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</time><strong>{fmt(day.temperature_min_c)}° – {fmt(day.temperature_max_c)}° C</strong><span>Humidity {day.humidity_pct ?? "—"}%</span><span>Wind {fmt(day.wind_speed_kmh)} km/h</span></article>)}</div> : <div className="prediction-empty">{selectedCell ? "Loading forecast…" : "Forecast unavailable until a cell is selected."}</div>}
      </section>

      <section className="panel prediction-panel">
        <div className="panel-heading"><div><h2>Recent prediction log</h2><p>Latest stored predictions across all cells</p></div><span className="recent-count">{log.total} total records</span></div>
        <div className="table-scroll"><table className="detection-table prediction-log-table"><thead><tr><th>Cell ID</th><th><button className="sort-button" onClick={() => setDescending((value) => !value)}>Date {descending ? "↓" : "↑"}</button></th><th>FWI</th><th>Risk level</th></tr></thead><tbody>{log.items.length ? log.items.map((row, i) => <tr key={`${row.cell_id}-${row.predicted_at}-${i}`}><td className="cell-id">{row.cell_id}</td><td className="detected-time">{dateTime(row.predicted_at)}</td><td>{fmt(row.risk_score, 2)}</td><td className={tierClass(row.risk_level)}>{row.risk_level}</td></tr>) : <tr><td colSpan="4" className="prediction-empty">No prediction rows available.</td></tr>}</tbody></table></div>
        <div className="prediction-pagination"><span>{log.total ? `${log.offset + 1}–${Math.min(log.offset + log.limit, log.total)} of ${log.total}` : "0 records"}</span><div><button disabled={!hasPrev} onClick={() => setLog((value) => ({ ...value, offset: Math.max(0, value.offset - value.limit) }))}>Previous</button><button disabled={!hasNext} onClick={() => setLog((value) => ({ ...value, offset: value.offset + value.limit }))}>Next</button></div></div>
      </section>
    </section>
  );
}
