from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FLOWGUARD_",
        extra="ignore",
    )

    app_name: str = "FlowGuard AI"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./flowguard.db"
    inference_provider: str = "mock"
    stepfun_api_key: str = ""
    stepfun_base_url: str = "https://api.stepfun.com/v1"
    stepfun_model: str = "step-5-preview"
    frame_interval_seconds: int = 3
    max_video_frames: int = 20
    sop_extractor_provider: str = "mock"
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_video_bytes: int = 500 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
