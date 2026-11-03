from fastapi import APIRouter, HTTPException

from app.services.update_cycle import run_update_cycle

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-update-cycle")
def run_update_cycle_now():
    result = run_update_cycle()
    if result.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="An update cycle is already running")
    return result
