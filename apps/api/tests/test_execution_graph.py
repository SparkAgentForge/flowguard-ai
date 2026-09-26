import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from flowguard_api.core.inference import InferenceFinding, VideoInferenceError
from flowguard_api.infrastructure.ai.providers import (
    DeepStreamInferenceAdapter,
    FfmpegFrameExtractor,
    Step5InferenceAdapter,
)
from flowguard_api.models import SopStep
from flowguard_api.services.execution_graph import compile_execution_graph, evaluate_evidence


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


def test_optional_background_does_not_reorder_required_steps() -> None:
    result = evaluate_evidence(
        steps(),
        [finding("label", 0), finding("scan", 9), finding("seal", 30)],
    )

    assert result.decision == "PASS"
    assert result.missing_steps == []
    assert result.misordered_steps == []
    assert compile_execution_graph(steps())["edges"] == [
        {"from": "scan", "to": "seal", "type": "required_before"}
    ]


def test_frame_extractor_samples_the_full_video(monkeypatch) -> None:
    monkeypatch.setattr(
        "flowguard_api.infrastructure.ai.providers.get_settings",
        lambda: SimpleNamespace(frame_interval_seconds=3, max_video_frames=20),
    )
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs):
        commands.append(command)
        if Path(command[0]).name == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="133.533534\n")
        if "-sseof" in command:
            Path(command[-1]).write_bytes(b"tail")
            return subprocess.CompletedProcess(command, 0)
        pattern = Path(command[-1])
        frame_count = int(command[command.index("-frames:v") + 1])
        for index in range(1, frame_count + 1):
            (pattern.parent / f"frame-{index:03d}.jpg").write_bytes(b"jpeg")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    frames = FfmpegFrameExtractor().extract(b"video", ".mp4")

    assert len(frames) == 20
    assert frames[-1][0] >= 132
    assert "fps=1/7." in commands[1][commands[1].index("-vf") + 1]
    assert all(frames[index][0] < frames[index + 1][0] for index in range(len(frames) - 1))


def test_step5_derives_ranges_from_real_evidence_frames() -> None:
    adapter = Step5InferenceAdapter()
    result = adapter._parse(
        {
            "findings": [
                {
                    "step_code": "scan",
                    "detected": True,
                    "confidence": 95,
                    "start_seconds": 99,
                    "end_seconds": 105,
                    "frame_timestamps": [16, 20, 99],
                }
            ]
        },
        steps()[:1],
        [0, 11, 16, 20, 32],
    )

    finding = result.findings[0]
    assert finding.frame_timestamps == [16, 20]
    assert finding.start_seconds == 16
    assert finding.end_seconds == 20


def test_step5_rejects_guessed_range_without_real_evidence() -> None:
    adapter = Step5InferenceAdapter()
    result = adapter._parse(
        {
            "findings": [
                {
                    "step_code": "scan",
                    "detected": True,
                    "confidence": 95,
                    "start_seconds": 16,
                    "end_seconds": 20,
                    "frame_timestamps": [],
                }
            ]
        },
        steps()[:1],
        [0, 11, 21, 32],
    )

    finding = result.findings[0]
    assert finding.detected is True
    assert finding.start_seconds is None
    assert finding.end_seconds is None
    assert finding.frame_timestamps == []


def test_step5_overlapping_ranges_become_uncertain() -> None:
    findings = [
        InferenceFinding(
            step_code="scan",
            detected=True,
            confidence=95,
            start_seconds=11,
            end_seconds=32,
            evidence="扫描动作",
            frame_timestamps=[11, 32],
        ),
        InferenceFinding(
            step_code="seal",
            detected=True,
            confidence=95,
            start_seconds=21,
            end_seconds=32,
            evidence="密封圈动作",
            frame_timestamps=[21, 32],
        ),
    ]

    normalized = Step5InferenceAdapter._enforce_temporal_order(findings, steps()[:2])
    assert normalized[0].start_seconds == 11
    assert normalized[1].start_seconds is None
    assert normalized[1].end_seconds is None
    assert normalized[1].occluded is True
    assert evaluate_evidence(steps()[:2], normalized).decision == "INSUFFICIENT_EVIDENCE"


def test_frame_extractor_reports_missing_media_tools(monkeypatch) -> None:
    monkeypatch.setattr(
        "flowguard_api.infrastructure.ai.providers.get_settings",
        lambda: SimpleNamespace(
            frame_interval_seconds=3,
            max_video_frames=20,
            ffmpeg_binary="missing-ffmpeg",
            ffprobe_binary="missing-ffprobe",
        ),
    )

    with pytest.raises(VideoInferenceError, match="未安装 ffmpeg/ffprobe"):
        FfmpegFrameExtractor().extract(b"video", ".mp4")


def test_step5_missing_step_remains_uncertain() -> None:
    result = Step5InferenceAdapter()._parse(
        {"findings": [{"step_code": "scan", "detected": True, "confidence": 90}]},
        steps()[:2],
    )

    assert result.findings[1].step_code == "seal"
    assert result.findings[1].detected is False
    assert result.findings[1].confidence == 0
    assert evaluate_evidence(steps()[:2], result.findings).decision == "INSUFFICIENT_EVIDENCE"


def test_step5_empty_findings_are_retried_once(monkeypatch) -> None:
    class Storage:
        def put(self, key, content):
            pass

        def get_url(self, key, expires_seconds=900):
            return f"https://rustfs.example/{key}"

    adapter = Step5InferenceAdapter(Storage())
    adapter.settings.stepfun_api_key = "test-key"
    adapter.frame_extractor.extract = lambda video, suffix: [(0, b"jpeg")]
    prompts = []

    def post_json(url, payload):
        prompts.append(payload["messages"][1]["content"][0]["text"])
        content = (
            "{}"
            if len(prompts) == 1
            else ('{"findings":[{"step_code":"scan","detected":false,"confidence":20}]}')
        )
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(adapter, "_post_json", post_json)
    result = adapter.analyze("video.mp4", b"video", steps()[:2])

    assert len(prompts) == 2
    assert prompts[0] != prompts[1]
    assert result.raw_response["model_responses"][0]["retried_empty_findings"] is True
    assert [finding.step_code for finding in result.findings] == ["scan", "seal"]

    with pytest.raises(VideoInferenceError, match="未返回可用的步骤判断"):
        adapter._parse({}, steps()[:2])


def test_step5_rejects_local_rustfs_url_before_model_request(monkeypatch) -> None:
    class Storage:
        def put(self, key, content):
            pass

        def get_url(self, key, expires_seconds=900):
            return f"http://127.0.0.1:9000/{key}"

    adapter = Step5InferenceAdapter(Storage())
    adapter.settings.stepfun_api_key = "test-key"
    adapter.frame_extractor.extract = lambda video, suffix: [(0, b"jpeg")]
    monkeypatch.setattr(
        adapter,
        "_post_json",
        lambda url, payload: (_ for _ in ()).throw(AssertionError("请求不应发出")),
    )

    with pytest.raises(VideoInferenceError, match="无法访问本机 RustFS"):
        adapter.analyze("video.mp4", b"video", steps()[:1])


def test_step5_retries_unparseable_response_and_combines_step_groups(monkeypatch) -> None:
    class Storage:
        def __init__(self) -> None:
            self.assets: dict[str, bytes] = {}

        def put(self, key: str, content: bytes) -> None:
            self.assets[key] = content

        def get_url(self, key: str, expires_seconds: int = 900) -> str:
            return f"https://rustfs.example/{key}"

    storage = Storage()
    adapter = Step5InferenceAdapter(storage)
    adapter.settings.stepfun_api_key = "test-key"
    adapter.settings.stepfun_steps_per_request = 3
    adapter.frame_extractor.extract = lambda video, suffix: [(0, b"jpeg"), (8, b"jpeg2")]
    requested_groups: list[list[str]] = []
    four_steps = [*steps(), SopStep(code="pack", sequence=4, name="包装", required=True)]

    def post_json(url: str, payload: dict) -> dict:
        finding_schema = payload["response_format"]["json_schema"]["schema"]["properties"][
            "findings"
        ]["items"]["properties"]
        codes = finding_schema["step_code"]["enum"]
        requested_groups.append(codes)
        if len(requested_groups) == 1:
            content = "not json"
        else:
            content = '{"findings":[' + ",".join(
                f'{{"step_code":"{code}","detected":true,"confidence":95}}' for code in codes
            ) + "]}"
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(adapter, "_post_json", post_json)
    result = adapter.analyze("video.mp4", b"video", four_steps)

    assert requested_groups == [["scan", "seal", "label"], ["scan", "seal", "label"], ["pack"]]
    assert [finding.step_code for finding in result.findings] == ["scan", "seal", "label", "pack"]
    assert len(storage.assets) == 2
    assert len(result.raw_response["model_responses"]) == 2
    assert result.raw_response["model_responses"][0]["retried_empty_findings"] is True


def test_step5_retries_incomplete_or_unscored_findings() -> None:
    adapter = Step5InferenceAdapter()
    assert adapter._needs_retry(
        {"findings": [{"step_code": "scan", "confidence": 90}]}, steps()[:2]
    )
    assert adapter._needs_retry(
        {
            "findings": [
                {"step_code": "scan", "confidence": 0},
                {"step_code": "seal", "confidence": 0},
            ]
        },
        steps()[:2],
    )
    assert not adapter._needs_retry(
        {
            "findings": [
                {"step_code": "scan", "confidence": 90},
                {"step_code": "seal", "confidence": 0},
            ]
        },
        steps()[:2],
    )


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
        part for part in captured["messages"][1]["content"] if part.get("type") == "image_url"
    ]
    assert len(storage.assets) == 2
    assert image_parts and all(
        not part["image_url"]["url"].startswith("data:") for part in image_parts
    )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["reasoning_effort"] == "low"
    assert captured["max_tokens"] == 8192
    assert result.raw_response["mode"] == "rustfs_frame_urls"
