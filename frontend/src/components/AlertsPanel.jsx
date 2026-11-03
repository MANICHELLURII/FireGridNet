import { useEffect, useState } from "react";
import { getAlerts } from "../api/client";

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    getAlerts().then(setAlerts).catch(() => setAlerts([]));
  }, []);

  return (
    <div className="alerts-panel">
      <h2>Recent Alerts</h2>
      {alerts.length === 0 && <p>No alerts yet.</p>}
      <ul>
        {alerts.map((alert, i) => (
          <li key={i} className={`alert alert-${alert.severity}`}>
            <strong>{alert.cell_id}</strong> — {alert.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
