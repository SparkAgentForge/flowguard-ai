"""Select the configured AI inference provider."""

from flowguard_api.config import get_settings
from flowguard_api.core.inference import VideoInferenceAdapter
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.providers import (
    DeepStreamInferenceAdapter,
    MockInferenceAdapter,
    Step5InferenceAdapter,
)


def get_video_inference_adapter(
    storage: FileStorage | None = None, work_order_id: str | None = None
) -> VideoInferenceAdapter:
    provider = get_settings().inference_provider.lower()
    if provider == "stepfun":
        return Step5InferenceAdapter(storage, work_order_id=work_order_id)
    if provider == "deepstream":
        return DeepStreamInferenceAdapter()
    return MockInferenceAdapter()
