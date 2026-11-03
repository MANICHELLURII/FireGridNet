from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    nasa_firms_map_key: str = ""
    openweather_api_key: str = ""
    update_interval_minutes: int = Field(default=30, gt=0)

    yolo_model_path: str = "app/ml_models/yolov8n_fire.pt"
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
