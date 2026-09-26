from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_PATH = Path(__file__).resolve()
_REPOSITORY_ROOT = next(
    (
        parent
        for parent in _CONFIG_PATH.parents
        if (parent / "apps" / "api" / "alembic.ini").is_file()
    ),
    None,
)
_ENV_FILES = tuple(
    str(path)
    for path in (
        (_REPOSITORY_ROOT / ".env" if _REPOSITORY_ROOT else None),
        Path.cwd() / ".env",
    )
    if path is not None
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Resolve the repository configuration even when PyCharm or an IDE
        # starts application.py with flowguard_api/ as the working directory.
        env_file=_ENV_FILES,
        env_prefix="FLOWGUARD_",
        extra="ignore",
    )

    app_name: str = "FlowGuard AI"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    database_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
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
    stepfun_steps_per_request: int = 10
    deepstream_base_url: str = "http://nvds-action-sop:8300"
    deepstream_api_key: str = ""
    deepstream_timeout_seconds: int = 300
    # Step 5 needs a denser timeline than the generic demo/provider settings.
    # Keep these separate so an old FLOWGUARD_FRAME_INTERVAL_SECONDS value
    # cannot silently turn an 80-second video into a handful of wide chunks.
    stepfun_frame_interval_seconds: float = 1.0
    stepfun_max_video_frames: int = 20
    frame_interval_seconds: int = 3
    max_video_frames: int = 20
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
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
