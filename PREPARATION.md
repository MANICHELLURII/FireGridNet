# FireGridNet — Project Brief

## In one minute

FireGridNet is a wildfire monitoring and decision-support prototype for a gridded forest area around Mannanur/Amrabad Tiger Reserve. It combines satellite hotspot detections and image-based fire/smoke detection with weather-based fire danger estimates. A web dashboard shows the monitored grid, recent events, risk summaries, and model reports. It does not deploy physical sensors or predict the path or time of a spreading fire.

## What happens in the system

1. **The area is divided into grid cells.** Cell boundaries, center points, and the reserve boundary are provided as GeoJSON and seeded into Supabase/PostGIS. Records are keyed by cell ID (for example, `MNR-00-00`).
2. **Fire detections are collected.** The scheduled backend cycle requests recent NASA FIRMS VIIRS hotspots, maps each hotspot coordinate into a grid cell, and stores it as a detection. The image endpoint accepts images from sources such as satellite, drone, webcam, or aerial imagery and runs the same YOLO model on them.
3. **Weather risk is calculated per cell.** The backend gets current OpenWeather observations (or accepts manually supplied weather), updates the cell’s FFMC, DMC, and DC moisture codes, calculates the Canadian Forest Fire Weather Index (FWI), and saves the score and risk band. State is persisted so the daily codes carry forward.
4. **The dashboard reads the stored data.** The React frontend calls the FastAPI API for grid cells, risk summaries/history, alerts, detections, forecasts, and reports. Supabase is the shared data store; the frontend does not query it directly.
5. **A background job keeps data fresh.** FastAPI starts an APScheduler job on startup (30-minute interval by default). It fetches weather for each grid cell, persists risk predictions, then ingests FIRMS detections. `POST /admin/run-update-cycle` can trigger the same cycle manually.

## Main parts

| Part | Role |
|---|---|
| `frontend/` | Vite + React dashboard: Dashboard, Live Map, Risk Prediction, Fire Detections, Reports, and placeholder Settings page. Leaflet displays spatial data. |
| `backend/app/main.py` | FastAPI entry point, CORS, health endpoint, router registration, and scheduler lifecycle. Interactive API docs are at `/docs`. |
| `backend/app/routers/` | HTTP endpoints for grid and cell details, predictions, detections and review status, alerts, dashboard summaries, reports, and manual update runs. |
| `backend/app/services/` | YOLO inference, FWI calculations/state, OpenWeather access, scheduled weather/FIRMS ingestion, Supabase access, and risk queries. |
| `backend/supabase_schema.sql` | PostGIS and tables for grid cells, detections, risk predictions, FWI state, and alerts; also includes the detection review-status migration. |
| `mannanur_grid.geojson`, `reserve_boundary.geojson`, `seed_mannanur_grid.sql` | Geographic inputs and seed data for the study area. The frontend also has display copies under `frontend/public/geo/`. |
| `backend/scripts/` and `backend/reports/` | YOLO runtime/sample evaluation and demo/verification utilities; generated JSON/CSV results are exposed in the Reports page. |

## Risk and detection in plain language

- **FWI is a weather-based danger index**, not a fire detector. The project uses the Canadian FWI equations and four reference labels: low (≤3), moderate (>3–10), high (>10–20), and extreme (>20). The per-cell moisture codes make the calculation depend on recent conditions, not just one weather reading.
- **YOLO is the image-based detector.** It labels fire/smoke objects using the configured checkpoint and a 0.4 detection confidence threshold, then stores the result, confidence, source, and best bounding box. FIRMS detections are a separate satellite-hotspot feed; they do not pass through YOLO.
- **Alerts and summaries organize evidence** from stored detections and risk records. Detection records can be reviewed as unverified, confirmed, false positive, or resolved.
- **Reports show operational and evaluation data**, including historical risk/detection trends and locally generated model timing/sample-quality reports. The sample quality script is not a full dataset or bounding-box mAP evaluation.

## What to know when presenting it

- The Canadian FWI thresholds and seasonal factors are reference values. Amrabad is tropical and near 16°N, so the project uses the nearest documented 20°N DMC day-length factors; the danger scale has not been locally calibrated. Present scores as comparative/provisional indicators, not validated local fire-danger forecasts.
- Standard FWI inputs are daily/noon weather and rainfall over the prior 24 hours. The current automated path uses current observations and OpenWeather’s 1-hour rain field (or zero), so automatic scores are provisional. Manual predictions are only as appropriate as the weather inputs supplied.
- Live integrations require configured Supabase, OpenWeatherMap, and NASA FIRMS credentials. The YOLO checkpoint is present at `backend/app/ml_models/yolov8n_fire.pt`; its suitability should be judged from the included sample evaluation and intended demo data.
- The README describes the intended deployment (React/Vite on Vercel, FastAPI on Render, Supabase/PostGIS), while actual availability depends on credentials, database schema/seed setup, and deployment configuration.

## Useful demo path

1. Open **Dashboard** for the overall grid and latest risk/detection summary.
2. Use **Live Map** to select a cell and inspect its risk and related details.
3. Show **Risk Prediction** to explain weather inputs, FWI output, and risk bands.
4. Show **Fire Detections** to review detections and their source/status.
5. Finish at **Reports** for trends and model evaluation results.

## Key files to orient yourself

- `README.md` — setup, deployment, evaluation commands, and calibration notes.
- `backend/app/main.py` — backend startup and scheduled job.
- `backend/app/services/update_cycle.py` — live data update flow.
- `backend/app/services/prediction_service.py` — FWI equations and persisted state.
- `backend/app/services/detection_service.py` — YOLO inference behavior.
- `frontend/src/App.jsx` — available dashboard routes.
- `backend/supabase_schema.sql` — database structure.
