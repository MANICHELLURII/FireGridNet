import { useCallback, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import CellDetailPanel from "../components/CellDetailPanel";
import RiskMap from "../components/RiskMap";

export default function LiveMap() {
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedCellId, setSelectedCellId] = useState(null);
  const [showReserveContext, setShowReserveContext] = useState(false);
  const [focusExtreme, setFocusExtreme] = useState(Boolean(location.state?.focusExtreme));
  const [focusCellId, setFocusCellId] = useState(location.state?.focusCellId || null);
  const handleExtremeFocusHandled = useCallback(() => {
    setFocusExtreme(false);
    if (location.state?.focusExtreme) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);
  const handleCellFocusHandled = useCallback(() => {
    setFocusCellId(null);
    if (location.state?.focusCellId) navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

  return (
    <div className="live-map-page">
      <div className="live-map-heading">
        <div><h2>Live grid map</h2><p>Explore cell-level risk and recent alerts.</p></div>
        <label className="reserve-context-toggle">
          <input type="checkbox" checked={showReserveContext} onChange={(event) => setShowReserveContext(event.target.checked)} />
          Show reserve context
        </label>
      </div>
      <div className="live-map-content">
        <div className="map-container">
          <RiskMap
            onCellSelect={setSelectedCellId}
            focusExtreme={focusExtreme}
            focusCellId={focusCellId}
            onCellFocusHandled={handleCellFocusHandled}
            onExtremeFocusHandled={handleExtremeFocusHandled}
            showReserveContext={showReserveContext}
          />
        </div>
        <CellDetailPanel cellId={selectedCellId} onClose={() => setSelectedCellId(null)} />
      </div>
    </div>
  );
}
