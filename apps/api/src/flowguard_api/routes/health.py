from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from flowguard_api.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str
    inference_provider: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="flowguard-api",
        environment=settings.environment,
        inference_provider=settings.inference_provider,
    )
