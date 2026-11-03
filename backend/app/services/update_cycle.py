"""Scheduled live weather and satellite-fire ingestion for the grid."""

import csv
import io
import logging
import threading
import time
from collections import Counter
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services.prediction_service import calculate_fwi
from app.services.supabase_client import get_supabase
from app.services.weather_service import fetch_current_weather_features

logger = logging.getLogger("uvicorn.error")

FIRMS_AREA = (78.76, 16.28, 78.90, 16.42)  # west, south, east, north
FIRMS_SOURCE = "VIIRS_SNPP_NRT"
FIRMS_DAY_RANGE = 1
WEATHER_CALL_DELAY_SECONDS = 1.0

_cycle_lock = threading.Lock()


def _error_label(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return type(exc).__name__


def _firms_confidence(value: str) -> float:
    """Convert FIRMS VIIRS confidence classes (or percent values) to [0, 1]."""
    normalized = value.strip().lower()
    classes = {"l": 0.3, "low": 0.3, "n": 0.6, "nominal": 0.6, "h": 0.9, "high": 0.9}
    if normalized in classes:
        return classes[normalized]
    try:
        numeric = float(normalized)
    except ValueError:
        return 0.5
    return max(0.0, min(1.0, numeric / 100.0 if numeric > 1.0 else numeric))


def _firms_detected_at(row: dict[str, str]) -> datetime:
    acquisition_date = row.get("acq_date", "").strip()
    acquisition_time = row.get("acq_time", "0000").strip().zfill(4)
    parsed = datetime.strptime(f"{acquisition_date} {acquisition_time}", "%Y-%m-%d %H%M")
    return parsed.replace(tzinfo=timezone.utc)


def _fetch_firms_rows(map_key: str) -> list[dict[str, str]]:
    west, south, east, north = FIRMS_AREA
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{map_key}/{FIRMS_SOURCE}/{west},{south},{east},{north}/{FIRMS_DAY_RANGE}"
    )
    response = httpx.get(url, timeout=45.0)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    if not reader.fieldnames:
        raise ValueError("FIRMS returned an empty CSV response")
    normalized_headers = {header.strip().lower() for header in reader.fieldnames if header}
    required = {"latitude", "longitude", "confidence"}
    if not required.issubset(normalized_headers):
        raise ValueError("FIRMS response is not a fire-detection CSV")
    return [
        {key.strip().lower(): value for key, value in row.items() if key and value is not None}
        for row in reader
    ]


def _ingest_firms_detections(sb, cells: list[dict]) -> dict:
    if not settings.nasa_firms_map_key:
        logger.warning("NASA FIRMS update skipped: NASA_FIRMS_MAP_KEY is not configured")
        return {
            "status": "skipped_no_map_key",
            "records_found": None,
            "detections_inserted": 0,
            "detections_unmatched": 0,
            "detection_insert_failures": 0,
            "error": "NASA_FIRMS_MAP_KEY is not configured",
        }

    try:
        rows = _fetch_firms_rows(settings.nasa_firms_map_key)
    except Exception as exc:
        logger.warning("NASA FIRMS request failed (%s)", _error_label(exc))
        return {
            "status": "failed",
            "records_found": None,
            "detections_inserted": 0,
            "detections_unmatched": 0,
            "detection_insert_failures": 0,
            "error": _error_label(exc),
        }

    inserted = 0
    unmatched = 0
    insert_failures = 0
    for row in rows:
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            confidence = _firms_confidence(row.get("confidence", ""))
            detected_at = _firms_detected_at(row)
        except (KeyError, TypeError, ValueError):
            unmatched += 1
            continue

        cell = next(
            (
                item for item in cells
                if item["min_lat"] <= latitude <= item["max_lat"]
                and item["min_lng"] <= longitude <= item["max_lng"]
            ),
            None,
        )
        if cell is None:
            unmatched += 1
            continue

        detection = {
            "cell_id": cell["cell_id"],
            "source": "nasa_firms",
            "fire_detected": True,
            "smoke_detected": False,
            "confidence": confidence,
            "bbox": None,
            "detected_at": detected_at.isoformat(),
        }
        try:
            sb.table("detections").insert(detection).execute()
            inserted += 1
        except Exception as exc:
            insert_failures += 1
            logger.warning(
                "FIRMS detection insert failed for cell %s (%s)",
                cell["cell_id"],
                _error_label(exc),
            )

    logger.info(
        "NASA FIRMS update complete: %d records found, %d detections inserted, %d unmatched, %d insert failures",
        len(rows), inserted, unmatched, insert_failures,
    )
    return {
        "status": "completed" if insert_failures == 0 else "partial",
        "records_found": len(rows),
        "detections_inserted": inserted,
        "detections_unmatched": unmatched,
        "detection_insert_failures": insert_failures,
        "error": None,
    }


def run_update_cycle() -> dict:
    """Fetch current weather and FIRMS hotspots, then persist live records."""
    if not _cycle_lock.acquire(blocking=False):
        logger.warning("Live update cycle skipped because another cycle is already running")
        return {"status": "already_running"}

    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    try:
        sb = get_supabase()
        cells = (
            sb.table("grid_cells")
            .select("cell_id,center_lat,center_lng,min_lat,min_lng,max_lat,max_lng")
            .order("cell_id")
            .execute()
            .data
        )
        total = len(cells)
        risk_updated = 0
        weather_failures = 0
        prediction_failures = 0
        database_unavailable = False
        risk_levels: Counter[str] = Counter()
        failure_samples: list[dict[str, str]] = []

        if not settings.openweather_api_key:
            weather_failures = total
            failure_samples.append({"cell_id": "*", "stage": "weather", "error": "OPENWEATHER_API_KEY is not configured"})
            logger.warning("Weather risk update skipped: OPENWEATHER_API_KEY is not configured")
        else:
            for index, cell in enumerate(cells, start=1):
                try:
                    features = fetch_current_weather_features(cell["center_lat"], cell["center_lng"])
                except Exception as exc:
                    weather_failures += 1
                    label = _error_label(exc)
                    if len(failure_samples) < 20:
                        failure_samples.append({"cell_id": cell["cell_id"], "stage": "weather", "error": label})
                    logger.warning("Weather fetch failed for %s (%s)", cell["cell_id"], label)
                else:
                    try:
                        prediction = calculate_fwi(cell["cell_id"], features)
                        sb.table("risk_predictions").insert(prediction.model_dump(mode="json")).execute()
                        risk_updated += 1
                        risk_levels[prediction.risk_level] += 1
                    except Exception as exc:
                        prediction_failures += 1
                        label = _error_label(exc)
                        if len(failure_samples) < 20:
                            failure_samples.append({"cell_id": cell["cell_id"], "stage": "prediction_or_insert", "error": label})
                        logger.warning("Risk prediction persistence failed for %s (%s)", cell["cell_id"], label)
                        if isinstance(exc, httpx.TransportError):
                            database_unavailable = True

                if index % 10 == 0 or index == total:
                    logger.info(
                        "Live risk update progress: %d of %d cells updated (%d weather failures, %d prediction failures)",
                        risk_updated, total, weather_failures, prediction_failures,
                    )
                if database_unavailable:
                    remaining = total - index
                    prediction_failures += remaining
                    logger.error("Stopping weather cycle early; Supabase transport failed at cell %s", cell["cell_id"])
                    break
                if index < total:
                    time.sleep(WEATHER_CALL_DELAY_SECONDS)

        firms_result = _ingest_firms_detections(sb, cells)
        duration = round(time.perf_counter() - started, 2)
        failed = weather_failures > 0 or prediction_failures > 0 or firms_result["status"] != "completed"
        result = {
            "status": "partial" if failed else "completed",
            "started_at": started_at.isoformat(),
            "duration_seconds": duration,
            "grid_cells_total": total,
            "risk_cells_updated": risk_updated,
            "weather_failures": weather_failures,
            "prediction_failures": prediction_failures,
            "risk_levels": {level: risk_levels[level] for level in ("low", "moderate", "high", "extreme")},
            "weather_failure_samples": failure_samples,
            "firms": firms_result,
        }
        logger.info(
            "Live update cycle %s in %.2fs: %d/%d risk updates; FIRMS %s (%s detections inserted)",
            result["status"], duration, risk_updated, total, firms_result["status"], firms_result["detections_inserted"],
        )
        return result
    finally:
        _cycle_lock.release()
