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
    inference_provider: str = "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
