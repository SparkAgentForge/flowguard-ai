from types import SimpleNamespace

from flowguard_api.core.inference import InferenceFinding
from flowguard_api.infrastructure.ai.providers import (
    DeepStreamInferenceAdapter,
    Step5InferenceAdapter,
)
from flowguard_api.models import SopStep
from flowguard_api.services.execution_graph import evaluate_evidence


def steps() -> list[SopStep]:
    return [
        SopStep(code="scan", sequence=1, name="扫描", required=True),
        SopStep(code="seal", sequence=2, name="密封圈", required=True),
        SopStep(code="label", sequence=3, name="标签", required=False),
    ]


def finding(
    code: str, start: int, detected: bool = True, confidence: int | None = None, **kwargs
) -> InferenceFinding:
    return InferenceFinding(
        step_code=code,
        detected=detected,
        confidence=confidence if confidence is not None else (95 if detected else 90),
        start_seconds=start if detected else None,
        end_seconds=start + 3 if detected else None,
        evidence=f"观察到 {code}" if detected else f"未观察到 {code}",
        frame_timestamps=[start, start + 1] if detected else [],
        **kwargs,
    )


def test_execution_graph_distinguishes_pass_missing_and_uncertain() -> None:
    passed = evaluate_evidence(steps(), [finding("scan", 0), finding("seal", 4)])
    assert passed.decision == "PASS"

    missing = evaluate_evidence(steps(), [finding("scan", 0), finding("seal", 4, detected=False)])
    assert missing.decision == "VIOLATION"
    assert missing.missing_steps == ["seal"]

    uncertain = evaluate_evidence(
        steps(), [finding("scan", 0), finding("seal", 4, occluded=True, confidence=40)]
    )
    assert uncertain.decision == "INSUFFICIENT_EVIDENCE"
    assert uncertain.review_requests[0]["step_code"] == "seal"


def test_deepstream_parser_maps_chunk_metadata_to_step_findings() -> None:
    payload = {
        "model": "deepstream-sop",
        "choices": [
            {
                "chunk_metadata_list": [
                    {
                        "chunk_idx": 2,
                        "start_time": 4,
                        "end_time": 8,
                        "cv_boundary_score": 0.91,
                        "response": "[seal] observed clearly",
                    }
                ]
            }
        ],
    }
    result = DeepStreamInferenceAdapter._parse_response(
        payload,
        [SimpleNamespace(code="seal", name="密封圈")],
    )
    assert result.findings[0].detected is True
    assert result.findings[0].chunk_idx == 2
    assert result.findings[0].cv_boundary_score == 0.91


def test_step5_sends_rustfs_frame_urls_instead_of_base64(monkeypatch) -> None:
    class FrameStorage:
        def __init__(self) -> None:
            self.assets: dict[str, bytes] = {}

        def put(self, key: str, content: bytes) -> None:
            self.assets[key] = content

        def get(self, key: str) -> bytes:
            return self.assets[key]

        def get_url(self, key: str, expires_seconds: int = 900) -> str:
            return f"https://rustfs.example/{key}?expires={expires_seconds}"

    storage = FrameStorage()
    adapter = Step5InferenceAdapter(storage)
    adapter.settings.stepfun_api_key = "test-key"
    adapter.frame_extractor.extract = lambda video, suffix: [(3, b"jpeg-1"), (6, b"jpeg-2")]
    captured: dict = {}

    def post_json(url: str, payload: dict) -> dict:
        captured.update(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"findings":[{"step_code":"scan","detected":true,'
                            '"confidence":90,"start_seconds":3,"end_seconds":6,'
                            '"evidence":"扫码动作","frame_timestamps":[3,6]}]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(adapter, "_post_json", post_json)
    result = adapter.analyze("normal.mp4", b"video", [steps()[0]])

    image_parts = [
        part
        for part in captured["messages"][1]["content"]
        if part.get("type") == "image_url"
    ]
    assert len(storage.assets) == 2
    assert image_parts and all(
        not part["image_url"]["url"].startswith("data:") for part in image_parts
    )
    assert result.raw_response["mode"] == "rustfs_frame_urls"
