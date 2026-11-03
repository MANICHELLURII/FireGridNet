import { NavLink, Outlet, useLocation } from "react-router-dom";

const navigation = [
  { label: "Dashboard", path: "/", icon: "▦" },
  { label: "Live Map", path: "/live-map", icon: "◎" },
  { label: "Risk Prediction", path: "/risk-prediction", icon: "◉" },
  { label: "Fire Detections", path: "/fire-detections", icon: "⌁" },
  { label: "Reports", path: "/reports", icon: "▤" },
  { label: "Settings", path: "/settings", icon: "⚙" },
];

const pageDescriptions = {
  "/": "Wildfire intelligence overview",
  "/live-map": "Live grid conditions and recent alerts",
  "/risk-prediction": "Cell conditions, regional risk and forecast",
  "/fire-detections": "Review live and historical fire signals",
  "/reports": "Exportable operational and historical summaries",
  "/settings": "Coming soon",
};

export default function Sidebar() {
  const { pathname } = useLocation();
  const currentPage = navigation.find((item) => item.path === pathname) ?? navigation[0];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">♨</div>
          <div>
            <div className="brand-name">FireGridNet</div>
            <div className="brand-caption">WILDFIRE INTELLIGENCE</div>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
              {item.path === "/live-map" && <span className="nav-live-dot" aria-label="Live" />}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-bottom-mark" aria-hidden="true">FG</div>
          <div>
            <strong>FireGridNet</strong>
            <span>Wildfire monitoring</span>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div>
            <div className="topbar-eyebrow">FIREGRIDNET <span>/</span> OPERATIONS</div>
            <h1>{currentPage.label}</h1>
            <p>{pageDescriptions[pathname] ?? "Wildfire intelligence overview"}</p>
          </div>
          <div className="topbar-accent" aria-hidden="true"><span /> Amrabad Tiger Reserve</div>
        </header>
        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
