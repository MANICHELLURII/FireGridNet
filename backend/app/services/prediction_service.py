"""Daily Canadian Forest Fire Weather Index (FWI) calculations.

Equations follow Van Wagner and Pickett (1985), the official equations
accompanying Van Wagner (1987), with latitude factors from Lawson & Armitage
(2008), Appendix 3. WeatherFeatures are expected to represent daily weather.
"""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from app.models.schemas import RiskPrediction, WeatherFeatures
from app.services.supabase_client import get_supabase

# Appendix 3, Table A3.1: 20°N DMC effective day-length factors. Amrabad is
# about 16°N, so this is the nearest documented latitude row. The special
# equatorial constant applies only from 10°N to 10°S.
DMC_DAY_LENGTH_20N = (7.9, 8.4, 8.9, 9.5, 9.9, 10.2, 10.1, 9.7, 9.1, 8.6, 8.1, 7.8)

# Appendix 3, Table A3.2: Northern Hemisphere DC seasonal factors.
DC_DAY_LENGTH_NORTH = (-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6)

STARTUP_CODES = {"ffmc": 85.0, "dmc": 6.0, "dc": 15.0}


def _ffmc(previous: float, temperature: float, humidity: float, wind: float, rain: float) -> float:
    moisture = 147.2 * (101.0 - previous) / (59.5 + previous)
    if rain > 0.5:
        effective_rain = rain - 0.5
        if moisture <= 150.0:
            moisture += 42.5 * effective_rain * math.exp(-100.0 / (251.0 - moisture)) * (1.0 - math.exp(-6.93 / effective_rain))
        else:
            moisture += 42.5 * effective_rain * math.exp(-100.0 / (251.0 - moisture)) * (1.0 - math.exp(-6.93 / effective_rain)) + 0.0015 * (moisture - 150.0) ** 2 * effective_rain ** 0.5
        moisture = min(moisture, 250.0)

    ed = 0.942 * humidity**0.679 + 11.0 * math.exp((humidity - 100.0) / 10.0) + 0.18 * (21.1 - temperature) * (1.0 - math.exp(-0.115 * humidity))
    if moisture > ed:
        ko = 0.424 * (1.0 - (humidity / 100.0) ** 1.7) + 0.0694 * wind**0.5 * (1.0 - (humidity / 100.0) ** 8)
        kd = ko * 0.581 * math.exp(0.0365 * temperature)
        moisture = ed + (moisture - ed) * 10.0 ** (-kd)
    else:
        ew = 0.618 * humidity**0.753 + 10.0 * math.exp((humidity - 100.0) / 10.0) + 0.18 * (21.1 - temperature) * (1.0 - math.exp(-0.115 * humidity))
        if moisture < ew:
            kl = 0.424 * (1.0 - ((100.0 - humidity) / 100.0) ** 1.7) + 0.0694 * wind**0.5 * (1.0 - ((100.0 - humidity) / 100.0) ** 8)
            kw = kl * 0.581 * math.exp(0.0365 * temperature)
            moisture = ew - (ew - moisture) * 10.0 ** (-kw)
    return 59.5 * (250.0 - moisture) / (147.2 + moisture)


def _dmc(previous: float, temperature: float, humidity: float, rain: float, month: int) -> float:
    effective_rain = 0.92 * rain - 1.27 if rain > 1.5 else 0.0
    if effective_rain > 0.0:
        moisture = 20.0 + 280.0 / math.exp(0.023 * previous)
        if previous <= 33.0:
            b = 100.0 / (0.5 + 0.3 * previous)
        elif previous <= 65.0:
            b = 14.0 - 1.3 * math.log(previous)
        else:
            b = 6.2 * math.log(previous) - 17.2
        moisture_rain = moisture + 1000.0 * effective_rain / (48.77 + b * effective_rain)
        previous = max(0.0, 244.72 - 43.43 * math.log(max(moisture_rain - 20.0, 1e-12)))
    drying_temperature = max(temperature, -1.1)
    drying = 1.894 * (drying_temperature + 1.1) * (100.0 - humidity) * DMC_DAY_LENGTH_20N[month - 1] * 1e-6
    return max(0.0, previous + 100.0 * drying)


def _dc(previous: float, temperature: float, rain: float, month: int) -> float:
    if rain > 2.8:
        effective_rain = 0.83 * rain - 1.27
        moisture = 800.0 * math.exp(-previous / 400.0)
        moisture_rain = moisture + 3.937 * effective_rain
        previous = max(0.0, 400.0 * math.log(800.0 / moisture_rain))
    drying_temperature = max(temperature, -2.8)
    drying = max(0.0, 0.36 * (drying_temperature + 2.8) + DC_DAY_LENGTH_NORTH[month - 1])
    return previous + 0.5 * drying


def _indices(ffmc: float, dmc: float, dc: float, wind: float) -> tuple[float, float, float]:
    moisture = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
    isi = 0.208 * math.exp(0.05039 * wind) * 91.9 * math.exp(-0.1386 * moisture) * (1.0 + moisture**5.31 / 4.93e7)
    if dmc <= 0.4:
        bui = 0.8 * dmc * dc / (dmc + 0.4 * dc) if dmc + 0.4 * dc else 0.0
    else:
        bui = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (0.92 + (0.0114 * dmc) ** 1.7)
    bui = max(0.0, bui)
    f_d = 0.626 * bui**0.809 + 2.0 if bui <= 80.0 else 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))
    intensity = 0.1 * isi * f_d
    fwi = intensity if intensity <= 1.0 else math.exp(2.72 * (0.434 * math.log(intensity)) ** 0.647)
    return isi, bui, fwi


def _risk_level(fwi: float) -> str:
    # Use the four-level thresholds in the 2021 NRCan Ontario FWI classes:
    # Low 0–3, Moderate >3–10, High >10–20, Extreme >20. These are
    # operational reference bands, not a tropical-region calibration.
    if fwi <= 3.0:
        return "low"
    if fwi <= 10.0:
        return "moderate"
    if fwi <= 20.0:
        return "high"
    return "extreme"


def risk_level_for_fwi(fwi: float) -> str:
    """Classify an FWI score using the same bands as risk predictions."""
    return _risk_level(fwi)


def calculate_fwi(cell_id: str, features: WeatherFeatures) -> RiskPrediction:
    """Calculate today's FWI, carrying yesterday's moisture codes per cell."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    month = today.month
    sb = get_supabase()
    response = (
        sb.table("fwi_state")
        .select("ffmc,dmc,dc,previous_ffmc,previous_dmc,previous_dc,calculation_date")
        .eq("cell_id", cell_id)
        .limit(1)
        .execute()
    )
    row = response.data[0] if response.data else None
    if row is None:
        prior = STARTUP_CODES.copy()
        same_day_prior = prior
    else:
        same_date = str(row["calculation_date"])[:10] == today.isoformat()
        if same_date:
            prior = {"ffmc": row["previous_ffmc"], "dmc": row["previous_dmc"], "dc": row["previous_dc"]}
            same_day_prior = prior
        else:
            prior = {"ffmc": row["ffmc"], "dmc": row["dmc"], "dc": row["dc"]}
            same_day_prior = prior

    ffmc = _ffmc(float(prior["ffmc"]), features.temperature_c, features.humidity_pct, features.wind_speed_kmh, features.rainfall_mm)
    dmc = _dmc(float(prior["dmc"]), features.temperature_c, features.humidity_pct, features.rainfall_mm, month)
    dc = _dc(float(prior["dc"]), features.temperature_c, features.rainfall_mm, month)
    _, _, fwi = _indices(ffmc, dmc, dc, features.wind_speed_kmh)

    sb.table("fwi_state").upsert(
        {
            "cell_id": cell_id,
            "ffmc": ffmc,
            "dmc": dmc,
            "dc": dc,
            "previous_ffmc": same_day_prior["ffmc"],
            "previous_dmc": same_day_prior["dmc"],
            "previous_dc": same_day_prior["dc"],
            "calculation_date": today.isoformat(),
        },
        on_conflict="cell_id",
    ).execute()

    return RiskPrediction(
        cell_id=cell_id,
        risk_score=fwi,
        risk_level=_risk_level(fwi),
        features_used=features,
    )


def calculate_vulnerability(cell_id: str) -> dict:
    """Return an explainable 0–100 vulnerability score for a grid cell.

    Formula: score = 0.50 * pct_high_extreme + 0.30 * min(avg_fwi_recent / 50, 1) * 100
    + 0.20 * min(detection_frequency / 10, 1) * 100. Each component is on a
    0–100 scale. The recent FWI average uses up to the latest 10 predictions,
    weighted linearly from 1 (oldest in the window) to N (newest). The
    historical high/extreme percentage and detection frequency use all records.
    """
    sb = get_supabase()
    predictions = []
    offset = 0
    page_size = 1000
    while True:
        page = (
            sb.table("risk_predictions")
            .select("risk_level,risk_score,predicted_at")
            .eq("cell_id", cell_id)
            .order("predicted_at")
            .range(offset, offset + page_size - 1)
            .execute()
            .data
        )
        predictions.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    total_predictions = len(predictions)
    high_extreme_count = sum(
        1 for row in predictions if str(row.get("risk_level", "")).lower() in {"high", "extreme"}
    )
    pct_high_extreme = (high_extreme_count / total_predictions * 100) if total_predictions else 0.0

    recent_predictions = predictions[-10:]
    recent_scores = [float(row.get("risk_score") or 0.0) for row in recent_predictions]
    recent_weights = list(range(1, len(recent_scores) + 1))
    avg_fwi_recent = (
        sum(score * weight for score, weight in zip(recent_scores, recent_weights)) / sum(recent_weights)
        if recent_scores else 0.0
    )

    detection_response = (
        sb.table("detections")
        .select("id", count="exact")
        .eq("cell_id", cell_id)
        .or_("fire_detected.eq.true,smoke_detected.eq.true")
        .execute()
    )
    detection_frequency = detection_response.count or 0

    normalized_recent_fwi = min(max(avg_fwi_recent / 50.0, 0.0), 1.0) * 100.0
    normalized_detections = min(detection_frequency / 10.0, 1.0) * 100.0
    score = (
        0.50 * pct_high_extreme
        + 0.30 * normalized_recent_fwi
        + 0.20 * normalized_detections
    )

    return {
        "cell_id": cell_id,
        "score": round(score, 2),
        "components": {
            "pct_high_extreme": round(pct_high_extreme, 2),
            "high_extreme_predictions": high_extreme_count,
            "total_predictions": total_predictions,
            "avg_fwi_recent": round(avg_fwi_recent, 2),
            "recent_prediction_count": len(recent_scores),
            "detection_frequency": detection_frequency,
            "normalized_recent_fwi": round(normalized_recent_fwi, 2),
            "normalized_detection_frequency": round(normalized_detections, 2),
        },
        "formula": "0.50 * pct_high_extreme + 0.30 * min(avg_fwi_recent / 50, 1) * 100 + 0.20 * min(detection_frequency / 10, 1) * 100",
        "recent_fwi_weighting": "Latest up to 10 predictions; linear weights 1 (oldest) through N (newest).",
    }
