from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone
from threading import Lock


# Shared by the app lifecycle and read-only dashboard status endpoint.
scheduler = BackgroundScheduler(timezone="UTC")
_status_lock = Lock()
_last_run_at = None


def record_scheduler_run(event) -> None:
    """Track completed scheduler executions for point-in-time reports."""
    global _last_run_at
    with _status_lock:
        _last_run_at = datetime.now(timezone.utc).isoformat()


def scheduler_status() -> dict:
    job = scheduler.get_job("live-weather-and-firms-update")
    with _status_lock:
        last_run_at = _last_run_at
    next_run = getattr(job, "next_run_time", None) if job else None
    return {
        "active": scheduler.running,
        "last_run_at": last_run_at,
        "next_run_at": next_run.isoformat() if next_run else None,
        "interval_minutes": int(job.trigger.interval.total_seconds() // 60) if job and hasattr(job.trigger, "interval") else None,
    }
