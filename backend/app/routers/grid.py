from datetime import datetime, timedelta, timezone
import math
import re

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Query

from app.models.schemas import GridCell, DetectionResult, RiskPrediction
from app.services.supabase_client import get_supabase
from app.services import detection_service, prediction_service, weather_service
from app.services.risk_query_service import get_grid_cell_ids, latest_rows_by_cell

router = APIRouter(prefix="/grid", tags=["grid"])


def _cell_exists(cell_id: str) -> bool:
    return bool(
        get_supabase().table("grid_cells").select("cell_id").eq("cell_id", cell_id).limit(1).execute().data
    )


@router.get("/cells", response_model=list[GridCell])
def list_cells():
    """Return all defined grid cells covering the monitored forest area."""
    sb = get_supabase()
    res = sb.table("grid_cells").select("*").execute()
    return res.data


@router.get("/overview/risk-score")
def get_regional_risk_score():
    """Highest latest-per-cell FWI score for the monitored grid."""
    sb = get_supabase()
    cell_ids = get_grid_cell_ids(sb)
    latest = latest_rows_by_cell(
        sb, "risk_predictions", "cell_id,risk_score,risk_level,predicted_at", "predicted_at", cell_ids
    )
    top = max(latest.values(), key=lambda row: float(row.get("risk_score") or 0), default=None)
    return {
        "risk_score": float(top["risk_score"]) if top else None,
        "cell_id": top["cell_id"] if top else None,
        "risk_level": prediction_service.risk_level_for_fwi(float(top["risk_score"])) if top else None,
        "predicted_at": top.get("predicted_at") if top else None,
        "cells_with_prediction": len(latest),
        "total_grid_cells": len(cell_ids),
    }


def _predictions_in_window(sb, start: datetime, end: datetime, cell_ids: set[str]) -> dict:
    """Most recent prediction per cell inside one UTC calendar-day window."""
    latest = {}
    offset = 0
    page_size = 1000
    while True:
        rows = (
            sb.table("risk_predictions")
            .select("cell_id,risk_score,risk_level,predicted_at")
            .gte("predicted_at", start.isoformat())
            .lt("predicted_at", end.isoformat())
            .order("predicted_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
            .data
        )
        for row in rows:
            if row.get("cell_id") in cell_ids:
                latest.setdefault(row["cell_id"], row)
        if len(rows) < page_size:
            break
        offset += page_size
    return latest


@router.get("/overview/vulnerability")
def get_forest_vulnerability():
    """Summarize current high/extreme share, mean FWI, and 3-day mean trend."""
    sb = get_supabase()
    cell_ids = get_grid_cell_ids(sb)
    latest = latest_rows_by_cell(
        sb, "risk_predictions", "cell_id,risk_score,risk_level,predicted_at", "predicted_at", cell_ids
    )
    scores = [float(row["risk_score"]) for row in latest.values() if row.get("risk_score") is not None]
    high_extreme = sum(1 for row in latest.values() if str(row.get("risk_level", "")).lower() in {"high", "extreme"})

    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    tomorrow = today_start + timedelta(days=1)
    three_days_start = today_start - timedelta(days=3)
    today_rows = _predictions_in_window(sb, today_start, tomorrow, cell_ids)
    three_day_rows = _predictions_in_window(sb, three_days_start, three_days_start + timedelta(days=1), cell_ids)
    today_scores = [float(row["risk_score"]) for row in today_rows.values() if row.get("risk_score") is not None]
    prior_scores = [float(row["risk_score"]) for row in three_day_rows.values() if row.get("risk_score") is not None]
    today_average = sum(today_scores) / len(today_scores) if today_scores else None
    prior_average = sum(prior_scores) / len(prior_scores) if prior_scores else None
    change = today_average - prior_average if today_average is not None and prior_average is not None else None
    # A difference within 1% of the earlier mean (or 0.1 FWI when near zero) is stable.
    threshold = max(0.1, abs(prior_average or 0.0) * 0.01)
    trend = "unavailable" if change is None else "stable" if abs(change) <= threshold else "rising" if change > 0 else "falling"
    return {
        "high_extreme_percent": (high_extreme / len(latest) * 100) if latest else None,
        "high_extreme_cells": high_extreme,
        "cells_with_prediction": len(latest),
        "total_grid_cells": len(cell_ids),
        "average_fwi": sum(scores) / len(scores) if scores else None,
        "today_average_fwi": today_average,
        "three_days_ago_average_fwi": prior_average,
        "trend_change_fwi": change,
        "trend": trend,
        "today_cells_with_prediction": len(today_scores),
        "three_days_ago_cells_with_prediction": len(prior_scores),
        "trend_stable_threshold_fwi": threshold,
    }


@router.get("/overview/predictions")
def get_recent_predictions(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    descending: bool = True,
):
    """Paginated prediction log across all cells."""
    sb = get_supabase()
    response = (
        sb.table("risk_predictions")
        .select("cell_id,predicted_at,risk_score,risk_level", count="exact")
        .order("predicted_at", desc=descending)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {"items": response.data, "total": response.count or 0, "limit": limit, "offset": offset}


@router.get("/{cell_id}/risk-history")
def get_cell_risk_history(cell_id: str, days: int = Query(default=14, ge=1, le=365)):
    if not _cell_exists(cell_id):
        raise HTTPException(status_code=404, detail="Grid cell not found")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        get_supabase().table("risk_predictions")
        .select("cell_id,predicted_at,risk_score,risk_level")
        .eq("cell_id", cell_id)
        .gte("predicted_at", since)
        .order("predicted_at")
        .execute()
        .data
    )
    return {"cell_id": cell_id, "days": days, "history": rows}


@router.get("/{cell_id}/forecast")
def get_cell_forecast(cell_id: str):
    cell = (
        get_supabase().table("grid_cells").select("center_lat,center_lng").eq("cell_id", cell_id).limit(1).execute().data
    )
    if not cell:
        raise HTTPException(status_code=404, detail="Grid cell not found")
    try:
        return weather_service.get_forecast(cell[0]["center_lat"], cell[0]["center_lng"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"OpenWeatherMap forecast returned HTTP {exc.response.status_code}") from exc


@router.get("/{cell_id}/neighbor-exposure")
def get_neighbor_exposure(cell_id: str):
    """Rank adjacent cells by a transparent directional exposure estimate.

    Formula (0–100): 50 * downwind_indicator + 30 * min(FWI / 20, 1)
    + 20 * ((100 - humidity_pct) / 100). Downwind is 1 only when the neighbor's
    bearing is within 45 degrees of the downwind bearing, otherwise 0. The
    FWI and humidity terms describe the neighbor's present conditions. This
    is a relative screening estimate, not a validated fire-spread model or
    a time-to-impact prediction.
    """
    sb = get_supabase()
    all_cells = sb.table("grid_cells").select("cell_id,center_lat,center_lng").execute().data
    cells_by_id = {row["cell_id"]: row for row in all_cells}
    source = cells_by_id.get(cell_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Grid cell not found")
    match = re.fullmatch(r"MNR-(\d+)-(\d+)", cell_id)
    if not match:
        raise HTTPException(status_code=400, detail="Cell ID does not use the MNR-row-column format")
    source_row, source_col = map(int, match.groups())
    neighbors = []
    for candidate_id, candidate in cells_by_id.items():
        candidate_match = re.fullmatch(r"MNR-(\d+)-(\d+)", candidate_id)
        if not candidate_match:
            continue
        row, column = map(int, candidate_match.groups())
        if candidate_id != cell_id and abs(row - source_row) <= 1 and abs(column - source_col) <= 1:
            neighbors.append(candidate)

    latest = latest_rows_by_cell(
        sb, "risk_predictions", "cell_id,risk_score,risk_level,features_used,predicted_at", "predicted_at", set(cells_by_id)
    )
    source_prediction = latest.get(cell_id)
    wind_direction = (source_prediction or {}).get("features_used", {}).get("wind_direction_deg")
    wind_source = "stored_prediction"
    if wind_direction is None:
        # Existing prediction rows may predate direction capture. Get one live
        # OWM reading for this source cell rather than inventing a direction.
        try:
            current_weather = weather_service.fetch_current_weather_features(source["center_lat"], source["center_lng"])
            wind_direction = current_weather.wind_direction_deg
            wind_source = "openweathermap_live"
        except (RuntimeError, httpx.HTTPError):
            wind_direction = None
            wind_source = "unavailable"

    ranked = []
    for neighbor in neighbors:
        prediction = latest.get(neighbor["cell_id"])
        if not prediction or prediction.get("risk_score") is None:
            ranked.append({"cell_id": neighbor["cell_id"], "risk_score": None, "risk_level": None, "humidity_pct": None, "downwind": None, "exposure_score": None, "predicted_at": None})
            continue
        fwi = float(prediction["risk_score"])
        features = prediction.get("features_used") or {}
        humidity = features.get("humidity_pct")
        downwind = None
        score = None
        if wind_direction is not None and humidity is not None:
            lat1 = math.radians(float(source["center_lat"]))
            lat2 = math.radians(float(neighbor["center_lat"]))
            delta_lng = math.radians(float(neighbor["center_lng"]) - float(source["center_lng"]))
            bearing = (math.degrees(math.atan2(math.sin(delta_lng) * math.cos(lat2), math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lng))) + 360) % 360
            downwind_bearing = (float(wind_direction) + 180) % 360
            angular_difference = abs((bearing - downwind_bearing + 180) % 360 - 180)
            downwind = angular_difference <= 45
            score = 50.0 * int(downwind) + 30.0 * min(max(fwi / 20.0, 0.0), 1.0) + 20.0 * (100.0 - float(humidity)) / 100.0
        ranked.append({
            "cell_id": neighbor["cell_id"],
            "risk_score": fwi,
            "risk_level": prediction.get("risk_level"),
            "humidity_pct": humidity,
            "downwind": downwind,
            "exposure_score": round(score, 2) if score is not None else None,
            "predicted_at": prediction.get("predicted_at"),
        })
    ranked.sort(key=lambda item: (item["exposure_score"] is not None, item["exposure_score"] or -1, item["risk_score"] or -1), reverse=True)
    return {
        "cell_id": cell_id,
        "wind_direction_deg": wind_direction,
        "wind_direction_source": wind_source,
        "formula": "50 * downwind_indicator + 30 * min(FWI / 20, 1) + 20 * ((100 - humidity_pct) / 100)",
        "interpretation": "Relative directional exposure estimate only; not a validated fire-spread model or time estimate.",
        "neighbors": ranked,
    }


@router.get("/{cell_id}/risk", response_model=RiskPrediction)
def get_cell_risk(cell_id: str):
    """Latest risk prediction for a given grid cell."""
    sb = get_supabase()
    res = (
        sb.table("risk_predictions")
        .select("*")
        .eq("cell_id", cell_id)
        .order("predicted_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="No risk prediction found for this cell")
    return res.data[0]


@router.get("/{cell_id}/vulnerability")
def get_cell_vulnerability(cell_id: str):
    """Explainable 0–100 vulnerability score and its raw/normalized components."""
    if not _cell_exists(cell_id):
        raise HTTPException(status_code=404, detail="Grid cell not found")
    return prediction_service.calculate_vulnerability(cell_id)


@router.get("/{cell_id}/details")
def get_cell_details(cell_id: str):
    """Current risk, latest detection, vulnerability, and up to 20 history rows."""
    if not _cell_exists(cell_id):
        raise HTTPException(status_code=404, detail="Grid cell not found")

    sb = get_supabase()
    history = (
        sb.table("risk_predictions")
        .select("cell_id,risk_score,risk_level,features_used,predicted_at")
        .eq("cell_id", cell_id)
        .order("predicted_at", desc=True)
        .limit(20)
        .execute()
        .data
    )
    latest_detection = (
        sb.table("detections")
        .select("id,source,fire_detected,smoke_detected,confidence,detected_at")
        .eq("cell_id", cell_id)
        .order("detected_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    fwi_state = (
        sb.table("fwi_state")
        .select("ffmc,dmc,dc,calculation_date")
        .eq("cell_id", cell_id)
        .limit(1)
        .execute()
        .data
    )
    return {
        "cell_id": cell_id,
        "current_risk": history[0] if history else None,
        "latest_detection": latest_detection[0] if latest_detection else None,
        "fwi_state": fwi_state[0] if fwi_state else None,
        "vulnerability": prediction_service.calculate_vulnerability(cell_id),
        "history": history,
    }


@router.post("/{cell_id}/image", response_model=DetectionResult)
async def submit_cell_image(cell_id: str, source: str, file: UploadFile = File(...)):
    """
    Source-agnostic ingestion point: satellite tiler, drone, or webcam can all
    POST an image here for the same cell and get a detection result back.
    """
    image_bytes = await file.read()
    result = detection_service.run_detection(image_bytes, cell_id=cell_id, source=source)

    sb = get_supabase()
    sb.table("detections").insert(result.model_dump(mode="json")).execute()

    return result
