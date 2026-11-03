from fastapi import APIRouter

from app.models.schemas import DashboardSummary
from app.services.scheduler import scheduler
from app.services.risk_query_service import get_grid_cell_ids, latest_rows_by_cell
from app.services.supabase_client import get_supabase
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RISK_LEVELS = ("low", "moderate", "high", "extreme")


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """Return live Supabase counts and the latest detection events."""
    sb = get_supabase()

    grid_cell_ids = get_grid_cell_ids(sb)
    grid_cells_total = len(grid_cell_ids)
    latest_predictions = latest_rows_by_cell(
        sb,
        "risk_predictions",
        "cell_id,risk_level,predicted_at",
        "predicted_at",
        cell_ids=grid_cell_ids,
    )
    risk_distribution = {level: 0 for level in RISK_LEVELS}
    for prediction in latest_predictions.values():
        level = str(prediction.get("risk_level", "")).lower()
        if level in risk_distribution:
            risk_distribution[level] += 1

    cumulative_predictions = (
        sb.table("risk_predictions").select("id", count="exact").execute().count or 0
    )

    latest_detections = latest_rows_by_cell(
        sb,
        "detections",
        "cell_id,fire_detected,smoke_detected,detected_at",
        "detected_at",
        cell_ids=grid_cell_ids,
    )
    active_fires = sum(1 for detection in latest_detections.values() if detection.get("fire_detected"))
    recent_detections = (
        sb.table("detections")
        .select("id,cell_id,fire_detected,smoke_detected,confidence,detected_at")
        .order("detected_at", desc=True)
        .limit(8)
        .execute()
        .data
    )
    latest_prediction = (
        sb.table("risk_predictions")
        .select("predicted_at")
        .order("predicted_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    return {
        "active_fires": active_fires,
        "risk_distribution": risk_distribution,
        "cumulative_predictions": cumulative_predictions,
        "grid_cells_total": grid_cells_total,
        "cells_with_prediction": len(latest_predictions),
        "recent_detections": recent_detections,
        "latest_prediction_at": latest_prediction[0]["predicted_at"] if latest_prediction else None,
        "scheduler_active": scheduler.running,
        "update_interval_minutes": settings.update_interval_minutes,
    }
