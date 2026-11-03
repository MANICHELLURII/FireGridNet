from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.supabase_client import get_supabase

router = APIRouter(tags=["detections"])


class DetectionStatus(str, Enum):
    unverified = "unverified"
    confirmed = "confirmed"
    false_positive = "false_positive"
    resolved = "resolved"


class DetectionStatusUpdate(BaseModel):
    status: DetectionStatus


@router.get("/detections/recent")
def list_recent_detections(
    limit: int = Query(default=50, ge=1, le=200),
    source: str | None = None,
    status: DetectionStatus | None = None,
    cell_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Most recent detections with cell-center coordinates and optional filters."""
    sb = get_supabase()
    query = (
        sb.table("detections")
        .select("id,cell_id,source,fire_detected,smoke_detected,confidence,detected_at,status")
        .order("detected_at", desc=True)
        .limit(limit)
    )
    if source:
        query = query.eq("source", source)
    if status:
        query = query.eq("status", status.value)
    if cell_id:
        query = query.eq("cell_id", cell_id)
    if date_from:
        query = query.gte("detected_at", datetime.combine(date_from, time.min, tzinfo=timezone.utc).isoformat())
    if date_to:
        query = query.lt("detected_at", datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc).isoformat())

    try:
        rows = query.execute().data
    except Exception as exc:
        if "status" in str(exc).lower() and ("column" in str(exc).lower() or "schema cache" in str(exc).lower()):
            raise HTTPException(status_code=503, detail="Detection status migration is not applied. Run the detections status ALTER TABLE in backend/supabase_schema.sql.") from exc
        raise

    cell_ids = {row.get("cell_id") for row in rows if row.get("cell_id")}
    cells = (
        sb.table("grid_cells").select("cell_id,center_lat,center_lng").in_("cell_id", list(cell_ids)).execute().data
        if cell_ids else []
    )
    coords = {cell["cell_id"]: cell for cell in cells}
    return [
        {
            **row,
            "center_lat": coords.get(row.get("cell_id"), {}).get("center_lat"),
            "center_lng": coords.get(row.get("cell_id"), {}).get("center_lng"),
        }
        for row in rows
    ]


@router.patch("/grid/{cell_id}/detections/{detection_id}/status")
def update_detection_status(cell_id: str, detection_id: str, payload: DetectionStatusUpdate):
    """Set one detection's review status, scoped by both cell and detection ID."""
    sb = get_supabase()
    try:
        response = (
            sb.table("detections")
            .update({"status": payload.status.value})
            .eq("id", detection_id)
            .eq("cell_id", cell_id)
            .execute()
        )
    except Exception as exc:
        if "status" in str(exc).lower() and ("column" in str(exc).lower() or "schema cache" in str(exc).lower()):
            raise HTTPException(status_code=503, detail="Detection status migration is not applied. Run the detections status ALTER TABLE in backend/supabase_schema.sql.") from exc
        raise
    if not response.data:
        raise HTTPException(status_code=404, detail="Detection not found for this cell")
    return response.data[0]
