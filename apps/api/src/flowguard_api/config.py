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
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./flowguard.db"
    object_storage_endpoint: str = ""
    object_storage_public_endpoint: str = ""
    object_storage_bucket: str = "flowguard"
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_region: str = "us-east-1"
    inference_provider: str = "mock"
    stepfun_api_key: str = ""
    stepfun_base_url: str = "https://api.stepfun.com/v1"
    stepfun_model: str = "step-5-preview"
    stepfun_frame_url_expires_seconds: int = 900
    stepfun_timeout_seconds: int = 180
    deepstream_base_url: str = "http://nvds-action-sop:8300"
    deepstream_api_key: str = ""
    deepstream_timeout_seconds: int = 300
    frame_interval_seconds: int = 3
    max_video_frames: int = 20
    manual_review_confidence_threshold: int = 60
    sop_extractor_provider: str = "stepfun"
    sop_manual_page_dpi: int = 144
    sop_manual_max_pages: int = 50
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_video_bytes: int = 500 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
