import base64
import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from flowguard_api.config import get_settings
from flowguard_api.models import SopStep


class VideoInferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class InferenceFinding:
    step_code: str
    detected: bool
    confidence: int
    start_seconds: int | None
    end_seconds: int | None
    evidence: str
    frame_timestamps: list[int]


@dataclass(frozen=True)
class InferenceResult:
    provider: str
    model_name: str
    overall_pass: bool
    summary: str
    findings: list[InferenceFinding]
    raw_response: dict


class VideoInferenceAdapter(Protocol):
    def analyze(self, filename: str, video: bytes, steps: list[SopStep]) -> InferenceResult: ...


class MockInferenceAdapter:
    def analyze(self, filename: str, video: bytes, steps: list[SopStep]) -> InferenceResult:
        if not video:
            raise VideoInferenceError("视频内容为空")
        scenario = filename.lower()
        findings = []
        for index, step in enumerate(steps):
            detected = "normal" in scenario or "rework" in scenario or index != 1
            confidence = 41 if "occluded" in scenario and index == 1 else (94 if detected else 88)
            start = index * 9 if detected else None
            findings.append(
                InferenceFinding(
                    step_code=step.code,
                    detected=detected,
                    confidence=confidence,
                    start_seconds=start,
                    end_seconds=start + 7 if start is not None else None,
                    evidence=(
                        f"在 {start:02d}—{start + 7:02d} 秒观察到“{step.name}”对应动作"
                        if detected
                        else f"在预期时间窗口内未观察到“{step.name}”"
                    ),
                    frame_timestamps=[start, start + 3] if start is not None else [9, 12, 15],
                )
            )
        overall_pass = all(item.detected for item in findings)
        if overall_pass:
            summary = "所有必需步骤均已观察到"
        elif "occluded" in scenario:
            summary = "关键步骤画面受遮挡，需要人工复核"
        else:
            summary = "第 2 步未观察到，请核对视频证据"
        return InferenceResult(
            provider="mock",
            model_name="deterministic-demo",
            overall_pass=overall_pass,
            summary=summary,
            findings=findings,
            raw_response={"filename": filename, "mode": "mock"},
        )


class FfmpegFrameExtractor:
    def extract(self, video: bytes, suffix: str) -> list[tuple[int, bytes]]:
        settings = get_settings()
        with tempfile.TemporaryDirectory(prefix="flowguard-frames-") as temp_dir:
            root = Path(temp_dir)
            input_path = root / f"input{suffix}"
            input_path.write_bytes(video)
            pattern = root / "frame-%03d.jpg"
            command = [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(input_path),
                "-vf",
                f"fps=1/{settings.frame_interval_seconds},scale=960:-2",
                "-frames:v",
                str(settings.max_video_frames),
                str(pattern),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=120)
            except FileNotFoundError as error:
                raise VideoInferenceError("服务器未安装 ffmpeg，无法提取视频关键帧") from error
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise VideoInferenceError("视频关键帧提取失败") from error
            frames = sorted(root.glob("frame-*.jpg"))
            if not frames:
                raise VideoInferenceError("视频中没有可分析的画面")
            return [
                (index * settings.frame_interval_seconds, frame.read_bytes())
                for index, frame in enumerate(frames)
            ]


class Step5InferenceAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.frame_extractor = FfmpegFrameExtractor()

    def analyze(self, filename: str, video: bytes, steps: list[SopStep]) -> InferenceResult:
        if not self.settings.stepfun_api_key:
            raise VideoInferenceError("未配置 FLOWGUARD_STEPFUN_API_KEY")
        frames = self.frame_extractor.extract(video, Path(filename).suffix.lower() or ".mp4")
        content: list[dict] = [{"type": "text", "text": self._prompt(steps, frames)}]
        for timestamp, frame in frames:
            content.extend(
                [
                    {"type": "text", "text": f"时间戳：{timestamp} 秒"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64.b64encode(frame).decode()}"
                        },
                    },
                ]
            )
        payload = {
            "model": self.settings.stepfun_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是工业装配审计员。只根据给出的时间戳画面判断，"
                        "禁止补全未看到的动作。"
                    ),
                },
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.settings.stepfun_base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.settings.stepfun_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw_api_response = json.loads(response.read())
            message = raw_api_response["choices"][0]["message"]["content"]
            parsed = json.loads(message)
            return self._parse(parsed, steps)
        except (
            urllib.error.URLError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
            TypeError,
        ) as error:
            raise VideoInferenceError("Step 5 返回内容无法解析") from error

    def _prompt(self, steps: list[SopStep], frames: list[tuple[int, bytes]]) -> str:
        step_payload = [
            {
                "code": step.code,
                "sequence": step.sequence,
                "name": step.name,
                "evidence_requirements": step.evidence_requirements,
            }
            for step in steps
        ]
        timestamps = [timestamp for timestamp, _ in frames]
        return (
            "核对以下 SOP 步骤是否在按时间排序的画面中出现。缺少明确证据时 detected 必须为 false。"
            f"\nSOP：{json.dumps(step_payload, ensure_ascii=False)}"
            f"\n可用时间戳：{timestamps}"
            "\n仅输出 JSON：{overall_pass:boolean,summary:string,findings:[{step_code:string,"
            "detected:boolean,confidence:0到100整数,start_seconds:整数或null,end_seconds:整数或null,"
            "evidence:string,frame_timestamps:整数数组}]}。每个 SOP 步骤必须且只能出现一次。"
        )

    def _parse(self, payload: dict, steps: list[SopStep]) -> InferenceResult:
        by_code = {item.get("step_code"): item for item in payload.get("findings", [])}
        findings = []
        for step in steps:
            item = by_code.get(step.code)
            if not isinstance(item, dict):
                raise VideoInferenceError(f"Step 5 缺少步骤 {step.code} 的判断")
            findings.append(
                InferenceFinding(
                    step_code=step.code,
                    detected=bool(item.get("detected")),
                    confidence=max(0, min(100, int(item.get("confidence", 0)))),
                    start_seconds=item.get("start_seconds"),
                    end_seconds=item.get("end_seconds"),
                    evidence=str(item.get("evidence", "")),
                    frame_timestamps=[int(value) for value in item.get("frame_timestamps", [])],
                )
            )
        overall_pass = all(item.detected for item in findings)
        return InferenceResult(
            provider="stepfun",
            model_name=self.settings.stepfun_model,
            overall_pass=overall_pass,
            summary=str(payload.get("summary", "Step 5 视频检测完成")),
            findings=findings,
            raw_response=payload,
        )


def get_video_inference_adapter() -> VideoInferenceAdapter:
    provider = get_settings().inference_provider.lower()
    if provider == "stepfun":
        return Step5InferenceAdapter()
    return MockInferenceAdapter()
