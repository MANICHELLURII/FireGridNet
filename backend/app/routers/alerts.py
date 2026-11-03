from fastapi import APIRouter

from app.models.schemas import Alert
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[Alert])
def list_recent_alerts(limit: int = 50):
    sb = get_supabase()
    res = (
        sb.table("alerts")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data
