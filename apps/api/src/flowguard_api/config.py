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
    sop_extractor_provider: str = "mock"
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
