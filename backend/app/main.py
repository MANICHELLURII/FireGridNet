import logging

import httpx
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.config import settings
from app.routers import grid, prediction, alerts, dashboard, admin, detections, reports
from app.services.scheduler import scheduler, record_scheduler_run
from app.services.update_cycle import run_update_cycle

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="FireGridNet API",
    description="Source-agnostic wildfire detection, risk prediction and GIS decision support.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(httpx.TransportError)
async def handle_upstream_transport_error(request: Request, exc: httpx.TransportError):
    """Return a logged, CORS-decorated service error for upstream network failures."""
    logger.error(
        "Upstream transport failed for %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "A configured upstream service is temporarily unavailable."},
    )

app.include_router(grid.router)
app.include_router(prediction.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(detections.router)
app.include_router(reports.router)


@app.on_event("startup")
def start_live_update_scheduler():
    if scheduler.running:
        return
    scheduler.add_listener(record_scheduler_run, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        run_update_cycle,
        trigger="interval",
        minutes=settings.update_interval_minutes,
        id="live-weather-and-firms-update",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Live update scheduler started: every %d minutes", settings.update_interval_minutes)


@app.on_event("shutdown")
def stop_live_update_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Live update scheduler stopped")


@app.get("/health")
def health():
    return {"status": "ok"}
