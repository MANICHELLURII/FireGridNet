# FireGridNet

Source-agnostic wildfire detection, risk prediction, and GIS-driven decision support.

## Stack

- **Frontend:** Vite + React → Vercel
- **Backend:** FastAPI → Render
- **Database:** Supabase (Postgres) + PostGIS
- **Detection:** YOLOv8 (fire/smoke)
- **Fire danger:** Canadian Forest Fire Weather Index System (CFFWIS)

## Project layout

```
firegridnet/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py             # env-based settings
│   │   ├── routers/
│   │   │   ├── grid.py           # grid cells, image ingestion (source-agnostic)
│   │   │   ├── prediction.py     # weather-based risk scoring
│   │   │   ├── alerts.py
│   │   │   └── admin.py          # manual live-update trigger
│   │   ├── services/
│   │   │   ├── detection_service.py   # YOLO inference wrapper
│   │   │   ├── prediction_service.py  # Daily CFFWIS calculation and state
│   │   │   ├── update_cycle.py        # scheduled weather and FIRMS ingestion
│   │   │   └── supabase_client.py
│   │   ├── models/schemas.py     # Pydantic request/response models
│   │   └── ml_models/            # YOLO checkpoint (gitignored)
│   ├── requirements.txt
│   ├── supabase_schema.sql       # run in Supabase SQL editor
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx                # dashboard shell
    │   ├── components/
    │   │   ├── RiskMap.jsx        # Leaflet map, colored by risk_level
    │   │   └── AlertsPanel.jsx
    │   └── api/client.js          # axios wrapper for the FastAPI backend
    └── .env.example
```

## 1. Supabase setup

1. Create a project at supabase.com.
2. Open the SQL editor, paste and run `backend/supabase_schema.sql`.
3. Copy your Project URL and `service_role` key into `backend/.env` (see `.env.example`).
4. Run the included `seed_mannanur_grid.sql` after creating the schema to add the sample cells. The schema includes `fwi_state`, which stores each cell's rolling FFMC, DMC, and DC values.

## 2. Backend (local dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
```

API docs at `http://localhost:8000/docs`.

Set `OPENWEATHER_API_KEY` and `NASA_FIRMS_MAP_KEY` in `backend/.env` to enable live weather and NASA FIRMS ingestion. The background update runs every `UPDATE_INTERVAL_MINUTES` (default `30`). Call `POST /admin/run-update-cycle` to trigger it manually.

**Before image-based detection fully works you still need to:**
- Fine-tune or source a YOLOv8 fire/smoke checkpoint and drop it at the path set by `YOLO_MODEL_PATH`.
- Configure Supabase, OpenWeatherMap, and NASA FIRMS credentials. Automatic weather-based updates use current OpenWeather observations as provisional inputs for risk calculations.

## 3. Frontend (local dev)

```bash
cd frontend
npm install
cp .env.example .env   # point VITE_API_BASE_URL at your local or deployed backend
npm run dev
```

## 4. Deploy

- **Frontend → Vercel:** import the `frontend/` folder as the project root, framework preset "Vite", set `VITE_API_BASE_URL` to your Render backend URL.
- **Backend → Render:** new Web Service, root directory `backend/`, build command `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Add the same env vars as `.env.example`.

## 5. Model execution evaluation

Run from `backend/` to measure the YOLO detection service's cold first-inference time, warmed per-image latency (min/mean/median/p95/max), and throughput. By default it benchmarks `scripts/sample_fire.png`; pass `--images-dir` to use a local image dataset. It writes a JSON summary and per-inference CSV under `backend/reports/`, which the Reports page displays and can export/print.

```bash
python scripts/evaluate_execution.py
python scripts/evaluate_execution.py --images-dir path/to/dfire/test/images --iterations 5
```

For a small, deterministic image-level quality check against labeled D-Fire test samples, run:

```bash
python scripts/evaluate_dfire_sample.py --per-class 3
```

This downloads a stratified sample from the D-Fire test split and writes per-image CSV and JSON metrics under `backend/reports/`. It reports image-level fire/smoke precision, recall, F1, and category accuracy; it is not a full-dataset evaluation and does not compute bounding-box mAP. Neither evaluation script writes records to Supabase.

## Notes

- **Public deployment security:** the API currently has no authentication or rate limiting. In particular, the manual update-cycle, image-ingestion, and risk-prediction endpoints can trigger external/API work or write to Supabase. Add access controls and abuse limits before exposing a configured backend to the public internet. Keep the Supabase service-role key server-side and never put it in the frontend.
- Detection is deliberately source-agnostic: `POST /grid/{cell_id}/image?source=satellite|drone|webcam|aerial` accepts an image from any origin and runs the same YOLO pipeline. This is the core novelty claim from the literature review — no physical sensors are deployed by this system.
- Render's free/starter tier is CPU-only; keep the YOLO checkpoint small (YOLOv8n) for acceptable inference latency in a demo.
- Risk prediction uses the standard daily Canadian Forest Fire Weather Index equations (Van Wagner and Pickett, 1985; Van Wagner, 1987), with per-cell FFMC, DMC, and DC state persisted in `fwi_state`. New cells start at FFMC 85, DMC 6, and DC 15. The API's four risk labels use the 2021 NRCan Ontario FWI reference thresholds: low ≤3, moderate >3–10, high >10–20, extreme >20. These are reference thresholds from a Canadian regional classification, not a locally calibrated Amrabad danger scale.
- **Known calibration limitation:** Amrabad Tiger Reserve is near 16°N, outside the Canadian latitudes for which the FWI System was originally designed. Calculations use the documented 20°N monthly DMC day-length factors and Northern Hemisphere monthly DC factors from Lawson and Armitage (2008), Appendix 3 (Tables A3.1–A3.2). This is an approximation; tropical fuel and climate calibration should be discussed in the project report.
- **Weather-input limitation:** CFFWIS expects daily noon weather and rainfall accumulated over the preceding 24 hours. The manual prediction endpoint accepts `rainfall_mm` as supplied, but the existing OpenWeather auto endpoint currently fills it from the current-observation API's 1-hour rain field (or zero). Its auto FWI result is therefore provisional until that endpoint provides 24-hour rainfall and standard observation timing.
- References: [Van Wagner & Pickett, Equations and FORTRAN Program (1985)](https://climatelibrary.ecc.gov.nt.ca/dataset/c36897fc-7ee0-44ea-9e8a-3b2147911139/resource/a4df620a-52bc-4a78-afed-2e6a8dd226d4/download/fwi_equation_19973.pdf); [Lawson & Armitage, Weather Guide (2008)](https://publications.gc.ca/collections/collection_2009/nrcan/Fo134-8-2008E.pdf); [NRCan Ontario FWI class study (2021)](https://publications.gc.ca/collections/collection_2022/rncan-nrcan/Fo123-2-29-2021-eng.pdf).
