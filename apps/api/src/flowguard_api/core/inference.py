"""Provider-neutral video inference contract.

The application and domain layers consume this contract.  Step 5, DeepStream,
and the deterministic demo provider implement it in the infrastructure layer.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class SopStepLike(Protocol):
    code: str
    sequence: int
    name: str
    evidence_requirements: list[str] | None


class VideoInferenceError(RuntimeError):
    """Raised when a provider cannot produce a valid inference result."""


@dataclass(frozen=True)
class InferenceFinding:
    step_code: str
    detected: bool
    confidence: int
    start_seconds: int | None
    end_seconds: int | None
    evidence: str
    frame_timestamps: list[int]
    occluded: bool = False
    evidence_score: int | None = None
    chunk_idx: int | None = None
    cv_boundary_score: float | None = None


@dataclass(frozen=True)
class InferenceResult:
    provider: str
    model_name: str
    overall_pass: bool
    summary: str
    findings: list[InferenceFinding]
    raw_response: dict


class VideoInferenceAdapter(Protocol):
    def analyze(
        self,
        filename: str,
        video: bytes,
        steps: Sequence[SopStepLike],
    ) -> InferenceResult: ...

