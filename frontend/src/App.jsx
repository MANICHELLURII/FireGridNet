import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import LiveMap from "./pages/LiveMap";
import RiskPrediction from "./pages/RiskPrediction";
import FireDetections from "./pages/FireDetections";
import Reports from "./pages/Reports";
import ComingSoon from "./pages/ComingSoon";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Sidebar />}>
          <Route index element={<Dashboard />} />
          <Route path="live-map" element={<LiveMap />} />
          <Route path="risk-prediction" element={<RiskPrediction />} />
          <Route path="fire-detections" element={<FireDetections />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<ComingSoon title="Settings" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
