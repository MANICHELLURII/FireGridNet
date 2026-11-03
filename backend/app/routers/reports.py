from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from statistics import mean

from fastapi import APIRouter, Query

from app.routers.grid import get_forest_vulnerability
from app.services.risk_query_service import get_grid_cell_ids, latest_rows_by_cell
from app.services.scheduler import scheduler_status
from app.services.supabase_client import get_supabase
from app.services.prediction_service import risk_level_for_fwi

router = APIRouter(prefix="/reports", tags=["reports"])
RISK_LEVELS = ("low", "moderate", "high", "extreme")
PAGE_SIZE = 1000
REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"


@router.get("/evaluation")
def get_execution_evaluation():
    """Return the latest locally generated model runtime and sample evaluation reports."""
    payload = {}
    for key, filename in (("execution", "execution_latest.json"), ("accuracy", "model_accuracy_latest.json")):
        path = REPORT_DIR / filename
        payload[key] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return payload


def _read_pages(make_query) -> list[dict]:
    rows = []
    offset = 0
    while True:
        page = make_query(offset).range(offset, offset + PAGE_SIZE - 1).execute().data
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _daily_predictions(sb, start: datetime, end: datetime) -> dict[str, dict[str, float]]:
    rows_by_day: dict[str, dict[str, float]] = {}
    offset = 0
    while True:
        page = (
            sb.table("risk_predictions")
            .select("cell_id,risk_score,predicted_at")
            .gte("predicted_at", start.isoformat())
            .lt("predicted_at", end.isoformat())
            .order("predicted_at", desc=True)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
            .data
        )
        for row in page:
            if not row.get("cell_id") or row.get("risk_score") is None:
                continue
            day = str(row["predicted_at"])[:10]
            # Latest value per cell/day prevents cells with more scheduler runs
            # from outweighing cells with fewer rows in the daily mean.
            rows_by_day.setdefault(day, {}).setdefault(row["cell_id"], float(row["risk_score"]))
        if len(page) < PAGE_SIZE:
            return rows_by_day
        offset += PAGE_SIZE


@router.get("/snapshot")
def get_operational_snapshot():
    """Current point-in-time summary from Supabase and the live scheduler."""
    sb = get_supabase()
    cell_ids = get_grid_cell_ids(sb)
    latest = latest_rows_by_cell(
        sb,
        "risk_predictions",
        "cell_id,risk_score,risk_level,predicted_at",
        "predicted_at",
        cell_ids,
    )
    risk_breakdown = {level: 0 for level in RISK_LEVELS}
    for row in latest.values():
        level = str(row.get("risk_level", "")).lower()
        if level in risk_breakdown:
            risk_breakdown[level] += 1

    top = max(latest.values(), key=lambda row: float(row.get("risk_score") or 0), default=None)
    vulnerability = get_forest_vulnerability()

    try:
        detections = _read_pages(
            lambda offset: sb.table("detections")
            .select("id,source,status")
            .order("detected_at", desc=True)
        )
        status_available = True
    except Exception as exc:
        message = str(exc).lower()
        if "status" not in message or not ("column" in message or "schema cache" in message):
            raise
        detections = _read_pages(
            lambda offset: sb.table("detections")
            .select("id,source")
            .order("detected_at", desc=True)
        )
        status_available = False

    sources = Counter(row.get("source") or "unknown" for row in detections)
    statuses = Counter(row.get("status") for row in detections if row.get("status"))
    scheduler = scheduler_status()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grid": {
            "total_cells": len(cell_ids),
            "cells_with_latest_prediction": len(latest),
            "risk_level_breakdown": risk_breakdown,
            "highest_risk_cell": ({
                "cell_id": top["cell_id"],
                "fwi": float(top["risk_score"]),
                "risk_level": risk_level_for_fwi(float(top["risk_score"])),
                "predicted_at": top.get("predicted_at"),
            } if top else None),
        },
        "forest_vulnerability": vulnerability,
        "detections": {
            "total": len(detections),
            "by_source": dict(sources),
            "by_status": dict(statuses) if status_available else None,
            "status_column_available": status_available,
        },
        "scheduler": scheduler,
    }


@router.get("/trend")
def get_historical_trend(days: int = Query(default=14, ge=1, le=90)):
    """Daily means from the latest per-cell prediction in each UTC day window.

    Every requested calendar day is returned to expose gaps explicitly:
    average_fwi stays null on days with no prediction rows; detection_count is
    the actual number of matching detection rows (zero when none were stored).
    """
    sb = get_supabase()
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    daily_predictions = _daily_predictions(sb, start, end)

    detection_day_counts = Counter()
    offset = 0
    while True:
        page = (
            sb.table("detections")
            .select("detected_at")
            .gte("detected_at", start.isoformat())
            .lt("detected_at", end.isoformat())
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
            .data
        )
        for row in page:
            detection_day_counts[str(row["detected_at"])[:10]] += 1
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    points = []
    for day_offset in range(days):
        day = first_day + timedelta(days=day_offset)
        key = day.isoformat()
        cell_values = daily_predictions.get(key, {})
        points.append({
            "date": key,
            "average_fwi": round(mean(cell_values.values()), 4) if cell_values else None,
            "cells_with_prediction": len(cell_values),
            "detection_count": detection_day_counts.get(key, 0),
            "has_prediction_data": bool(cell_values),
            "has_detection_data": key in detection_day_counts,
        })
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "days": days, "timezone": "UTC", "points": points}
