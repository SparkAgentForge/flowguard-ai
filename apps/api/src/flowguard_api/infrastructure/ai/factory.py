"""Select the configured AI inference provider."""

from flowguard_api.config import get_settings
from flowguard_api.core.inference import VideoInferenceAdapter
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.providers import (
    DeepStreamInferenceAdapter,
    MockInferenceAdapter,
    Step5InferenceAdapter,
)


def get_video_inference_adapter(storage: FileStorage | None = None) -> VideoInferenceAdapter:
    provider = get_settings().inference_provider.lower()
    if provider == "stepfun":
        return Step5InferenceAdapter(storage)
    if provider == "deepstream":
        return DeepStreamInferenceAdapter()
    return MockInferenceAdapter()

