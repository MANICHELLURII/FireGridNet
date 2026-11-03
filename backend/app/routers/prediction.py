from fastapi import APIRouter

from app.models.schemas import WeatherFeatures, RiskPrediction
from app.services import prediction_service
from app.services.supabase_client import get_supabase
from app.services.weather_service import fetch_current_weather_features

router = APIRouter(prefix="/predict-risk", tags=["prediction"])


@router.post("/{cell_id}", response_model=RiskPrediction)
def predict_for_cell(cell_id: str, features: WeatherFeatures):
    """Run the risk model on manually supplied weather features."""
    prediction = prediction_service.calculate_fwi(cell_id, features)

    sb = get_supabase()
    sb.table("risk_predictions").insert(prediction.model_dump(mode="json")).execute()

    return prediction


@router.post("/{cell_id}/auto", response_model=RiskPrediction)
def predict_for_cell_auto(cell_id: str, lat: float, lng: float):
    """Pull live weather from OpenWeatherMap for the cell's coordinates, then predict."""
    features = fetch_current_weather_features(lat, lng)
    prediction = prediction_service.calculate_fwi(cell_id, features)

    sb = get_supabase()
    sb.table("risk_predictions").insert(prediction.model_dump(mode="json")).execute()

    return prediction
