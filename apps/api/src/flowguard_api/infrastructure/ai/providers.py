import json
import mimetypes
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from flowguard_api.config import get_settings
from flowguard_api.core.inference import (
    InferenceFinding,
    InferenceResult,
    SopStepLike,
    VideoInferenceError,
)
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient


class MockInferenceAdapter:
    def analyze(
        self, filename: str, video: bytes, steps: list[SopStepLike]
    ) -> InferenceResult:
        if not video:
            raise VideoInferenceError("视频内容为空")
        scenario = filename.lower()
        findings = []
        for index, step in enumerate(steps):
            is_seal_step = step.code in {"install_seal", "seal"} or (
                len(steps) == 2 and index == 1
            )
            detected = "normal" in scenario or "rework" in scenario or not is_seal_step
            confidence = 41 if "occluded" in scenario and is_seal_step else (94 if detected else 88)
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
                    occluded="occluded" in scenario and is_seal_step,
                    evidence_score=confidence,
                    chunk_idx=index,
                )
            )
        overall_pass = all(item.detected for item in findings)
        if overall_pass:
            summary = "所有必需步骤均已观察到"
        elif "occluded" in scenario:
            summary = "关键步骤画面受遮挡，需要人工复核"
        else:
            summary = "安装绿色密封圈未观察到，请核对视频证据"
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
    def __init__(self, storage: FileStorage | None = None) -> None:
        self.settings = get_settings()
        self.frame_extractor = FfmpegFrameExtractor()
        self.storage = storage
        self.client = Step5VisionClient(self.settings)

    def analyze(
        self, filename: str, video: bytes, steps: list[SopStepLike]
    ) -> InferenceResult:
        if not self.settings.stepfun_api_key:
            raise VideoInferenceError("未配置 FLOWGUARD_STEPFUN_API_KEY")
        return self._analyze_frames(filename, video, steps)

    def _analyze_frames(
        self, filename: str, video: bytes, steps: list[SopStepLike]
    ) -> InferenceResult:
        frames = self.frame_extractor.extract(video, Path(filename).suffix.lower() or ".mp4")
        if self.storage is None or not hasattr(self.storage, "get_url"):
            raise VideoInferenceError("Step 5 帧分析需要配置 RustFS，以提供帧图片 URL")
        frame_prefix = f"step5-frames/{uuid4().hex}"
        frame_assets: list[str] = []
        content: list[dict] = [{"type": "text", "text": self._prompt(steps, frames)}]
        for timestamp, frame in frames:
            frame_key = f"{frame_prefix}/frame-{timestamp:06d}.jpg"
            try:
                self.storage.put(frame_key, frame)
                frame_url = self.storage.get_url(
                    frame_key, self.settings.stepfun_frame_url_expires_seconds
                )
            except Exception as error:
                raise VideoInferenceError("视频帧写入 RustFS 或生成 URL 失败") from error
            frame_assets.append(frame_key)
            content.extend(
                [
                    {"type": "text", "text": f"时间戳：{timestamp} 秒"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": frame_url,
                        },
                    },
                ]
            )
        payload = self._chat_payload(steps, content)
        raw_api_response = self._post_json(
            f"{self.settings.stepfun_base_url.rstrip('/')}/chat/completions", payload
        )
        parsed = self._response_payload(raw_api_response)
        return self._parse(
            parsed,
            steps,
            raw_response={
                "api_response": raw_api_response,
                "mode": "rustfs_frame_urls",
                "frame_asset_keys": frame_assets,
            },
        )

    def _chat_payload(self, steps: list[SopStepLike], content: list[dict]) -> dict:
        return {
            "model": self.settings.stepfun_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是工业装配审计员。只根据给出的视觉证据判断，"
                        "禁止补全未看到的动作。"
                    ),
                },
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }

    def _post_json(self, url: str, payload: dict) -> dict:
        return self.client.post_json(url, payload)

    @staticmethod
    def _response_payload(raw_api_response: dict) -> dict:
        return Step5VisionClient.response_payload(raw_api_response)

    def _prompt(self, steps: list[SopStepLike], frames: list[tuple[int, bytes]]) -> str:
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
            "evidence:string,frame_timestamps:整数数组,occluded:boolean,evidence_score:整数}]}。"
            "每个 SOP 步骤必须且只能出现一次。"
        )

    def _parse(
        self, payload: dict, steps: list[SopStepLike], raw_response: dict | None = None
    ) -> InferenceResult:
        by_code = {
            item.get("step_code"): item
            for item in (payload.get("findings") or [])
            if isinstance(item, dict)
        }
        findings = []
        for step in steps:
            item = by_code.get(step.code)
            if not isinstance(item, dict):
                raise VideoInferenceError(f"Step 5 缺少步骤 {step.code} 的判断")
            findings.append(
                InferenceFinding(
                    step_code=step.code,
                    detected=bool(item.get("detected")),
                    confidence=max(0, min(100, _coerce_int(item.get("confidence"), 0))),
                    start_seconds=_as_int(item.get("start_seconds")),
                    end_seconds=_as_int(item.get("end_seconds")),
                    evidence=str(item.get("evidence") or ""),
                    frame_timestamps=[
                        _coerce_int(value, 0) for value in (item.get("frame_timestamps") or [])
                    ],
                    occluded=bool(item.get("occluded", False)),
                    evidence_score=max(
                        0,
                        min(
                            100,
                            _coerce_int(
                                item.get("evidence_score", item.get("confidence")), 0
                            ),
                        ),
                    ),
                    chunk_idx=_as_int(item.get("chunk_idx")),
                    cv_boundary_score=_as_float(item.get("cv_boundary_score")),
                )
            )
        overall_pass = all(item.detected for item in findings)
        return InferenceResult(
            provider="stepfun",
            model_name=self.settings.stepfun_model,
            overall_pass=overall_pass,
            summary=str(payload.get("summary", "Step 5 视频检测完成")),
            findings=findings,
            raw_response=raw_response or payload,
        )


class DeepStreamInferenceAdapter:
    """Thin client for NVIDIA's unchanged DeepStream SOP microservice.

    DeepStream owns GEBD/chunk boundaries. FlowGuard intentionally maps its
    chunk metadata into our provider-neutral finding contract and performs the
    final execution-graph decision outside the NVIDIA service.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze(
        self, filename: str, video: bytes, steps: list[SopStepLike]
    ) -> InferenceResult:
        file_id = self._upload_file(filename, video)
        prompt = (
            "Return JSON evidence for this SOP. Preserve each step code in brackets, "
            "for example [scan_part]. Never infer an action that is not visible.\n"
            + "\n".join(
                f"[{step.code}] {step.sequence}. {step.name}: "
                f"{'; '.join(step.evidence_requirements or ['动作清晰可见'])}"
                for step in steps
            )
        )
        payload = {
            "model": "deepstream-sop",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_video", "file_id": file_id},
                    ],
                }
            ],
            "stream": False,
            "chunking_options": {"algorithm": "ddm-net"},
        }
        raw_response = self._post_json(
            f"{self.settings.deepstream_base_url.rstrip('/')}/v1/chat/completions", payload
        )
        return self._parse_response(raw_response, steps)

    def _upload_file(self, filename: str, video: bytes) -> str:
        boundary = "----FlowGuardDeepStreamBoundary"
        mime = mimetypes.guess_type(filename)[0] or "video/mp4"
        body = b"".join(
            [
                (
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                    f"filename=\"{Path(filename).name}\"\r\nContent-Type: {mime}\r\n\r\n"
                ).encode(),
                video,
                (
                    f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\""
                    "\r\n\r\nvision\r\n"
                ).encode(),
                f"--{boundary}--\r\n".encode(),
            ]
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.settings.deepstream_api_key:
            headers["Authorization"] = f"Bearer {self.settings.deepstream_api_key}"
        request = urllib.request.Request(
            f"{self.settings.deepstream_base_url.rstrip('/')}/v1/files",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.settings.deepstream_timeout_seconds
            ) as response:
                result = json.loads(response.read())
            file_id = result.get("id") or result.get("file_id")
            if not file_id:
                raise ValueError("DeepStream files API 未返回文件 ID")
            return str(file_id)
        except (urllib.error.URLError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise VideoInferenceError("DeepStream 视频上传失败") from error

    def _post_json(self, url: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.settings.deepstream_api_key:
            headers["Authorization"] = f"Bearer {self.settings.deepstream_api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.settings.deepstream_timeout_seconds
            ) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError, TypeError) as error:
            raise VideoInferenceError("DeepStream 请求失败或返回内容无法解析") from error

    @staticmethod
    def _parse_response(payload: dict, steps: list[SopStepLike]) -> InferenceResult:
        choices = payload.get("choices", [])
        metadata = choices[0].get("chunk_metadata_list", []) if choices else []
        if not isinstance(metadata, list):
            metadata = []
        findings: list[InferenceFinding] = []
        for step in steps:
            matches = []
            for chunk in metadata:
                if not isinstance(chunk, dict) or chunk.get("chunk_idx") == -1:
                    continue
                text = str(chunk.get("response", ""))
                if step.code.lower() in text.lower() or step.name in text:
                    matches.append((chunk, text))
            if matches:
                chunk, text = matches[0]
                start = _as_int(chunk.get("start_time"))
                end = _as_int(chunk.get("end_time"))
                confidence = (
                    85
                    if not any(word in text.lower() for word in ("遮挡", "occluded", "blocked"))
                    else 45
                )
                findings.append(
                    InferenceFinding(
                        step_code=step.code,
                        detected=True,
                        confidence=confidence,
                        start_seconds=start,
                        end_seconds=end,
                        evidence=(
                            text
                            or f"DeepStream 在 chunk {chunk.get('chunk_idx')} 中观察到该步骤"
                        ),
                        frame_timestamps=[value for value in (start, end) if value is not None],
                        occluded=confidence < 60,
                        evidence_score=confidence,
                        chunk_idx=_as_int(chunk.get("chunk_idx")),
                        cv_boundary_score=_as_float(chunk.get("cv_boundary_score")),
                    )
                )
            else:
                findings.append(
                    InferenceFinding(
                        step_code=step.code,
                        detected=False,
                        confidence=35,
                        start_seconds=None,
                        end_seconds=None,
                        evidence=f"DeepStream chunk 结果中没有步骤 {step.code} 的明确证据",
                        frame_timestamps=[],
                        evidence_score=35,
                    )
                )
        return InferenceResult(
            provider="deepstream",
            model_name=str(payload.get("model", "deepstream-sop")),
            overall_pass=all(item.detected for item in findings),
            summary="DeepStream chunk 已返回，最终结论由 FlowGuard 执行图判定",
            findings=findings,
            raw_response=payload,
        )


def _coerce_int(value: object, default: int) -> int:
    parsed = _as_int(value)
    return parsed if parsed is not None else default


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
