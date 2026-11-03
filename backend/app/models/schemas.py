from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GridCell(BaseModel):
    cell_id: str
    center_lat: float
    center_lng: float
    # bounding box of the cell, for map rendering
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float


class DetectionResult(BaseModel):
    cell_id: Optional[str] = None
    source: str = Field(description="'satellite' | 'aerial' | 'drone' | 'webcam'")
    fire_detected: bool
    smoke_detected: bool
    confidence: float
    bbox: Optional[list[float]] = None  # [x1, y1, x2, y2]
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class WeatherFeatures(BaseModel):
    temperature_c: float
    humidity_pct: float
    rainfall_mm: float
    wind_speed_kmh: float
    wind_direction_deg: Optional[float] = None


class RiskPrediction(BaseModel):
    cell_id: str
    # FWI is a continuous, non-negative index and is not bounded to [0, 1].
    risk_score: float = Field(ge=0)
    risk_level: str  # low | moderate | high | extreme
    features_used: WeatherFeatures
    predicted_at: datetime = Field(default_factory=datetime.utcnow)


class Alert(BaseModel):
    cell_id: str
    alert_type: str  # "detection" | "risk_threshold"
    message: str
    severity: str  # low | moderate | high | extreme
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecentDetection(BaseModel):
    id: str
    cell_id: Optional[str] = None
    fire_detected: bool
    smoke_detected: bool
    confidence: float
    detected_at: datetime


class DashboardSummary(BaseModel):
    active_fires: int
    risk_distribution: dict[str, int]
    cumulative_predictions: int
    grid_cells_total: int
    cells_with_prediction: int
    recent_detections: list[RecentDetection]
    latest_prediction_at: Optional[datetime] = None
    scheduler_active: bool
    update_interval_minutes: int
