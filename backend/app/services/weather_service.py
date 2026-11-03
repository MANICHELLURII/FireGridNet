import httpx

from app.config import settings
from app.models.schemas import WeatherFeatures


OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"


def fetch_current_weather_features(lat: float, lng: float) -> WeatherFeatures:
    """Fetch current weather for a coordinate and normalize units for FWI."""
    if not settings.openweather_api_key:
        raise RuntimeError("OPENWEATHER_API_KEY is not configured")

    response = httpx.get(
        OPENWEATHER_CURRENT_URL,
        params={
            "lat": lat,
            "lon": lng,
            "appid": settings.openweather_api_key,
            "units": "metric",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    data = response.json()
    return WeatherFeatures(
        temperature_c=data["main"]["temp"],
        humidity_pct=data["main"]["humidity"],
        rainfall_mm=data.get("rain", {}).get("1h", 0.0),
        wind_speed_kmh=data["wind"]["speed"] * 3.6,
        wind_direction_deg=data.get("wind", {}).get("deg"),
    )


def get_forecast(lat: float, lng: float) -> dict:
    """Return the next seven daily forecasts from OpenWeather One Call 3.0."""
    if not settings.openweather_api_key:
        raise RuntimeError("OPENWEATHER_API_KEY is not configured")

    response = httpx.get(
        OPENWEATHER_ONECALL_URL,
        params={
            "lat": lat,
            "lon": lng,
            "appid": settings.openweather_api_key,
            "units": "metric",
            "exclude": "current,minutely,hourly,alerts",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    data = response.json()
    days = []
    for item in data.get("daily", [])[:7]:
        temperature = item.get("temp", {})
        days.append({
            "date": item.get("dt"),
            "temperature_c": temperature.get("day"),
            "temperature_min_c": temperature.get("min"),
            "temperature_max_c": temperature.get("max"),
            "humidity_pct": item.get("humidity"),
            "wind_speed_kmh": round(float(item.get("wind_speed", 0.0)) * 3.6, 1),
        })
    return {"source": "OpenWeatherMap One Call 3.0", "days": days}
