import { useCallback, useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, Rectangle, Popup, GeoJSON, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { getCachedValue, getGridCells, getCellRisk } from "../api/client";

const RISK_COLORS = {
  low: "#4ade80",
  moderate: "#facc15",
  high: "#fb923c",
  extreme: "#ef4444",
};

const RISK_BATCH_SIZE = 20;
const RISK_RETRY_DELAY_MS = 500;

function MapEffects({ cells, risks, riskLoadComplete, focusExtreme, focusCellId, onCellSelect, onExtremeFocusHandled, onCellFocusHandled }) {
  const map = useMap();
  const didFitExtreme = useRef(false);
  const didFitGrid = useRef(false);
  const didFitCell = useRef(false);

  useEffect(() => {
    map.invalidateSize();
  }, [map]);

  useEffect(() => {
    if (!cells.length || didFitGrid.current) return;
    didFitGrid.current = true;
    const bounds = cells.reduce(
      (result, cell) => [
        [Math.min(result[0][0], cell.min_lat), Math.min(result[0][1], cell.min_lng)],
        [Math.max(result[1][0], cell.max_lat), Math.max(result[1][1], cell.max_lng)],
      ],
      [[cells[0].min_lat, cells[0].min_lng], [cells[0].max_lat, cells[0].max_lng]],
    );
    map.fitBounds(bounds, { padding: [8, 8], maxZoom: 14, animate: false });
    map.setZoom(Math.min(map.getZoom() + 0.25, 14), { animate: false });
  }, [cells, map]);

  useEffect(() => {
    if (!focusCellId || !cells.length || didFitCell.current) return;
    const cell = cells.find((candidate) => candidate.cell_id === focusCellId);
    if (!cell) return;
    didFitCell.current = true;
    map.fitBounds([[cell.min_lat, cell.min_lng], [cell.max_lat, cell.max_lng]], { padding: [120, 120], maxZoom: 14 });
    onCellSelect(cell.cell_id);
    onCellFocusHandled();
  }, [cells, focusCellId, map, onCellSelect, onCellFocusHandled]);

  useEffect(() => {
    if (!focusExtreme || !riskLoadComplete || didFitExtreme.current) return;
    didFitExtreme.current = true;
    const extremeCells = cells.filter((cell) => {
      const result = risks[cell.cell_id];
      return result?.status === "prediction" && result.risk?.risk_level === "extreme";
    });

    if (extremeCells.length) {
      const bounds = extremeCells.flatMap((cell) => [
        [cell.min_lat, cell.min_lng],
        [cell.max_lat, cell.max_lng],
      ]);
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 12 });

      const scores = extremeCells.map((cell) => risks[cell.cell_id].risk.risk_score);
      const highest = Math.max(...scores);
      const topCells = extremeCells.filter((cell) => risks[cell.cell_id].risk.risk_score === highest);
      if (topCells.length === 1) onCellSelect(topCells[0].cell_id);
    }
    onExtremeFocusHandled();
  }, [cells, risks, riskLoadComplete, focusExtreme, map, onCellSelect, onExtremeFocusHandled]);

  return null;
}

async function getCellRiskWithRetry(cellId) {
  try {
    return await getCellRisk(cellId);
  } catch (firstError) {
    // A 404 means there is no prediction yet, so retrying cannot change that.
    if (firstError.response?.status === 404) return null;

    await new Promise((resolve) => setTimeout(resolve, RISK_RETRY_DELAY_MS));
    try {
      return await getCellRisk(cellId);
    } catch (retryError) {
      if (retryError.response?.status === 404) return null;
      throw retryError;
    }
  }
}

export default function RiskMap({ onCellSelect, focusExtreme = false, onExtremeFocusHandled, focusCellId = null, onCellFocusHandled, showReserveContext = false }) {
  const cachedCells = getCachedValue("grid-cells") ?? [];
  const cachedRisks = Object.fromEntries(cachedCells.flatMap((cell) => {
    const risk = getCachedValue(`cell-risk:${cell.cell_id}`);
    return risk === undefined
      ? []
      : [[cell.cell_id, risk ? { status: "prediction", risk } : { status: "no_data" }]];
  }));
  const [cells, setCells] = useState(cachedCells);
  const [risks, setRisks] = useState(cachedRisks);
  const [reserveBoundary, setReserveBoundary] = useState(null);
  const [riskLoadComplete, setRiskLoadComplete] = useState(() => cachedCells.length > 0 && Object.keys(cachedRisks).length === cachedCells.length);
  const handleCellSelect = useCallback((cellId) => onCellSelect?.(cellId), [onCellSelect]);
  const handleExtremeFocusHandled = useCallback(() => onExtremeFocusHandled?.(), [onExtremeFocusHandled]);
  const handleCellFocusHandled = useCallback(() => onCellFocusHandled?.(), [onCellFocusHandled]);

  useEffect(() => {
    fetch("/geo/reserve_boundary.geojson")
      .then((response) => (response.ok ? response.json() : null))
      .then(setReserveBoundary)
      .catch(() => setReserveBoundary(null));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadCellsAndRisks() {
      const fetchedCells = await getGridCells();
      if (cancelled) return;

      setCells(fetchedCells);
      setRisks((current) => Object.fromEntries(fetchedCells.map((cell) => {
        if (current[cell.cell_id]) return [cell.cell_id, current[cell.cell_id]];
        const cachedRisk = getCachedValue(`cell-risk:${cell.cell_id}`);
        return [cell.cell_id, cachedRisk ? { status: "prediction", risk: cachedRisk } : { status: "loading" }];
      })));

      // Twenty concurrent lookups limits pressure on Supabase/PostgREST while
      // still loading a 240-cell grid in a small number of network rounds.
      for (let offset = 0; offset < fetchedCells.length; offset += RISK_BATCH_SIZE) {
        const batch = fetchedCells.slice(offset, offset + RISK_BATCH_SIZE);
        const riskEntries = await Promise.all(
          batch.map(async (cell) => {
            try {
              const risk = await getCellRiskWithRetry(cell.cell_id);
              return [cell.cell_id, risk ? { status: "prediction", risk } : { status: "no_data" }];
            } catch (error) {
              return [cell.cell_id, { status: "failed" }];
            }
          })
        );

        if (!cancelled) setRisks((current) => ({ ...current, ...Object.fromEntries(riskEntries) }));
      }
      if (!cancelled) setRiskLoadComplete(true);
    }

    loadCellsAndRisks().catch((error) => {
      console.error("Unable to load grid cells", error);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <MapContainer center={[16.35, 78.83]} zoom={12} zoomSnap={0.25} zoomDelta={0.25} style={{ height: "100%", width: "100%" }}>
      <MapEffects
        cells={cells}
        risks={risks}
        riskLoadComplete={riskLoadComplete}
        focusExtreme={focusExtreme}
        focusCellId={focusCellId}
        onCellSelect={handleCellSelect}
        onExtremeFocusHandled={handleExtremeFocusHandled}
        onCellFocusHandled={handleCellFocusHandled}
      />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attribution='Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
      />
      {showReserveContext && reserveBoundary && (
        <GeoJSON
          data={reserveBoundary}
          interactive={false}
          style={{
            color: "#6b7280",
            weight: 1,
            fillOpacity: 0.08,
          }}
        />
      )}
      {cells.map((cell) => {
        const result = risks[cell.cell_id] ?? { status: "loading" };
        const risk = result.status === "prediction" ? result.risk : null;
        const isFailed = result.status === "failed";
        const isLoading = result.status === "loading";
        const isNoData = result.status === "no_data";
        const pulsesForHighRisk = risk && ["high", "extreme"].includes(risk.risk_level);
        const color = risk
          ? RISK_COLORS[risk.risk_level] ?? "#a855f7"
          : isFailed
            ? "#a855f7"
            : "#d1d5db";
        return (
          <Rectangle
            key={cell.cell_id}
            eventHandlers={{ click: () => handleCellSelect(cell.cell_id) }}
            bounds={[
              [cell.min_lat, cell.min_lng],
              [cell.max_lat, cell.max_lng],
            ]}
            pathOptions={{
              className: pulsesForHighRisk ? "risk-cell-outline-pulse" : undefined,
              color: risk ? "#172a22" : isNoData || isLoading ? "#d1d5db" : color,
              fillColor: risk ? color : isFailed ? color : "#d1d5db",
              fillOpacity: risk ? 0.4 : isFailed ? 0.25 : 0.12,
              opacity: risk ? 0.9 : 0.7,
              weight: isFailed ? 2 : risk ? 1.55 : 1.2,
              ...(isFailed ? { dashArray: "4 3", weight: 2 } : {}),
            }}
          >
            <Popup>
              <strong>{cell.cell_id}</strong>
              <br />
              {risk
                ? `Risk: ${risk.risk_level} (FWI ${risk.risk_score.toFixed(1)})`
                : isFailed
                  ? "Risk lookup failed"
                  : isLoading
                    ? "Loading risk data…"
                    : "No prediction yet"}
            </Popup>
          </Rectangle>
        );
      })}
    </MapContainer>
  );
}
