import json
import math
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
from flowguard_api.core.media import is_media_tool_runtime_error, resolve_media_tool
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient
from flowguard_api.infrastructure.storage.providers import LocalFileStorage


class MockInferenceAdapter:
    def analyze(self, filename: str, video: bytes, steps: list[SopStepLike]) -> InferenceResult:
        if not video:
            raise VideoInferenceError("视频内容为空")
        scenario = filename.lower()
        findings = []
        for index, step in enumerate(steps):
            is_seal_step = step.code in {"install_seal", "seal"} or (len(steps) == 2 and index == 1)
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
        requested_interval = float(
            getattr(
                settings,
                "stepfun_frame_interval_seconds",
                getattr(settings, "frame_interval_seconds", 3),
            )
        )
        max_frames = int(
            getattr(
                settings,
                "stepfun_max_video_frames",
                getattr(settings, "max_video_frames", 20),
            )
        )
        if max_frames < 2 or not math.isfinite(requested_interval) or requested_interval <= 0:
            raise VideoInferenceError("视频抽帧配置无效")
        try:
            ffprobe = resolve_media_tool(
                getattr(settings, "ffprobe_binary", "ffprobe"), "ffprobe"
            )
            ffmpeg = resolve_media_tool(
                getattr(settings, "ffmpeg_binary", "ffmpeg"), "ffmpeg"
            )
        except FileNotFoundError as error:
            raise VideoInferenceError(
                "服务器未安装 ffmpeg/ffprobe，请安装 FFmpeg 后重试"
            ) from error
        with tempfile.TemporaryDirectory(prefix="flowguard-frames-") as temp_dir:
            root = Path(temp_dir)
            input_path = root / f"input{suffix}"
            input_path.write_bytes(video)
            try:
                probe = subprocess.run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(input_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                duration = float(probe.stdout.strip())
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError("无效视频时长")
            except subprocess.CalledProcessError as error:
                if is_media_tool_runtime_error(error):
                    raise VideoInferenceError(
                        "FFmpeg/ffprobe 安装不完整，请重新安装 FFmpeg 后重试"
                    ) from error
                raise VideoInferenceError(
                    "视频文件无法解析，可能已损坏或编码格式不受支持"
                ) from error
            except subprocess.TimeoutExpired as error:
                raise VideoInferenceError("读取视频时长超时，请检查视频文件后重试") from error
            except ValueError as error:
                raise VideoInferenceError("视频没有有效时长，无法进行分析") from error
            # Spread the configured frame budget over the complete video.  The
            # previous implementation reserved a tail frame and then rounded a
            # stretched interval; on a long video this produced very wide gaps
            # and, with a dense budget, duplicated the final timestamp.  A
            # one-second Step 5 timeline now stays stable and every returned
            # timestamp corresponds to a real extracted frame.
            requested_count = max(2, math.ceil(duration / requested_interval) + 1)
            frame_count = min(max_frames, requested_count)
            interval = (
                requested_interval
                if requested_count <= max_frames
                else max(0.01, duration / max(1, frame_count - 1))
            )
            pattern = root / "frame-%03d.jpg"
            command = [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(input_path),
                "-vf",
                f"fps=1/{interval:.6f}:start_time=0,scale=960:-2",
                "-frames:v",
                str(frame_count),
                str(pattern),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=120)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                if isinstance(error, subprocess.CalledProcessError) and is_media_tool_runtime_error(
                    error
                ):
                    raise VideoInferenceError(
                        "FFmpeg 安装不完整，无法提取视频关键帧，请重新安装后重试"
                    ) from error
                raise VideoInferenceError("视频关键帧提取失败，请检查视频编码格式") from error
            regular_frames = sorted(root.glob("frame-[0-9][0-9][0-9].jpg"))
            if not regular_frames:
                raise VideoInferenceError("视频中没有可分析的画面")
            frames = []
            seen_timestamps: set[int] = set()
            for index, frame in enumerate(regular_frames):
                timestamp = min(math.floor(duration), round(index * interval))
                if timestamp in seen_timestamps:
                    continue
                seen_timestamps.add(timestamp)
                frames.append((timestamp, frame.read_bytes()))
            final_timestamp = math.floor(duration)
            if frames and frames[-1][0] < final_timestamp:
                # fps filters can stop just before the exact duration.  Add a
                # genuine tail frame only when it contributes a new timestamp.
                tail_path = root / "frame-final.jpg"
                try:
                    subprocess.run(
                        [
                            ffmpeg,
                            "-v",
                            "error",
                            "-sseof",
                            f"-{min(1.0, max(0.1, duration / 2)):.3f}",
                            "-i",
                            str(input_path),
                            "-vf",
                            "scale=960:-2",
                            "-frames:v",
                            "1",
                            str(tail_path),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    if isinstance(
                        error, subprocess.CalledProcessError
                    ) and is_media_tool_runtime_error(error):
                        raise VideoInferenceError(
                            "FFmpeg 安装不完整，无法提取视频尾帧，请重新安装 FFmpeg 后重试"
                        ) from error
                    raise VideoInferenceError("视频尾帧提取失败，请检查视频编码格式") from error
                if not tail_path.exists():
                    raise VideoInferenceError("无法提取视频尾帧")
                frames.append((final_timestamp, tail_path.read_bytes()))
            if len(frames) < 2:
                raise VideoInferenceError("视频中没有足够的可分析画面")
            return frames


class Step5InferenceAdapter:
    STEPS_PER_REQUEST = 10

    def __init__(
        self, storage: FileStorage | None = None, work_order_id: str | None = None
    ) -> None:
        self.settings = get_settings()
        self.frame_extractor = FfmpegFrameExtractor()
        self.storage = storage
        self.work_order_id = work_order_id
        self.client = Step5VisionClient(self.settings)

    def analyze(self, filename: str, video: bytes, steps: list[SopStepLike]) -> InferenceResult:
        if not self.settings.stepfun_api_key:
            raise VideoInferenceError("未配置 FLOWGUARD_STEPFUN_API_KEY")
        return self._analyze_frames(filename, video, steps)

    def _analyze_frames(
        self, filename: str, video: bytes, steps: list[SopStepLike]
    ) -> InferenceResult:
        if not steps:
            raise VideoInferenceError("SOP 没有可检查的步骤")
        frames = self.frame_extractor.extract(video, Path(filename).suffix.lower() or ".mp4")
        if self.storage is None or isinstance(self.storage, LocalFileStorage):
            raise VideoInferenceError("Step 5 帧分析需要配置 RustFS 存储")
        frame_prefix = (
            f"step5-frames/{self.work_order_id}/{uuid4().hex}"
            if self.work_order_id
            else f"step5-frames/{uuid4().hex}"
        )
        frame_assets: list[str] = []
        for timestamp, frame in frames:
            frame_key = f"{frame_prefix}/frame-{timestamp:06d}.jpg"
            try:
                self.storage.put(frame_key, frame)
            except Exception as error:
                raise VideoInferenceError("视频帧写入 RustFS 失败") from error
            frame_assets.append(frame_key)
        findings: list[InferenceFinding] = []
        model_responses: list[dict] = []
        steps_per_request = max(
            1,
            min(
                len(steps),
                getattr(self.settings, "stepfun_steps_per_request", self.STEPS_PER_REQUEST),
            ),
        )
        # A long video is observed through overlapping windows. This keeps
        # action boundaries visible to Step 5 while preventing the old global
        # frame budget from turning a 133-second video into seven-second gaps.
        windows = self._analysis_windows(frames)
        for window_index, window in enumerate(windows):
            for start in range(0, len(steps), steps_per_request):
                group = steps[start : start + steps_per_request]
                sampled_timestamps = [timestamp for timestamp, _ in window]
                frame_parts = [
                    (timestamp, self.client.image_part(frame, "image/jpeg"))
                    for timestamp, frame in window
                ]
                content: list[dict] = [{"type": "text", "text": self._prompt(group, window)}]
                for timestamp, frame_part in frame_parts:
                    content.extend(
                        [
                            {"type": "text", "text": f"时间戳：{timestamp} 秒"},
                            frame_part,
                        ]
                    )
                raw_api_response = self._post_json(
                    f"{self.settings.stepfun_base_url.rstrip('/')}/chat/completions",
                    self._chat_payload(group, content, sampled_timestamps),
                )
                try:
                    parsed = self._response_payload(raw_api_response)
                except VideoInferenceError:
                    parsed = {}
                retried = False
                if self._needs_retry(parsed, group):
                    retry_content = [
                        {
                            "type": "text",
                            "text": self._compact_prompt(group, sampled_timestamps),
                        },
                        *content[1:],
                    ]
                    raw_api_response = self._post_json(
                        f"{self.settings.stepfun_base_url.rstrip('/')}/chat/completions",
                        self._chat_payload(group, retry_content, sampled_timestamps),
                    )
                    parsed = self._response_payload(raw_api_response)
                    retried = True
                window_findings = self._parse(parsed, group, sampled_timestamps).findings
                findings.extend(window_findings)
                model_responses.append(
                    {
                        "window_index": window_index,
                        "window_start_seconds": (
                            sampled_timestamps[0] if sampled_timestamps else None
                        ),
                        "window_end_seconds": (
                            sampled_timestamps[-1] if sampled_timestamps else None
                        ),
                        "step_codes": [step.code for step in group],
                        "sampled_timestamps": sampled_timestamps,
                        "parsed": parsed,
                        "usage": raw_api_response.get("usage"),
                        "finish_reason": raw_api_response.get("choices", [{}])[0].get(
                            "finish_reason"
                        ),
                        "retried_empty_findings": retried,
                    }
                )
        findings = self._merge_window_findings(findings, steps)
        findings = self._enforce_temporal_order(findings, steps)
        required_codes = {step.code for step in steps if step.required}
        detected_codes = {
            finding.step_code
            for finding in findings
            if finding.detected and finding.start_seconds is not None
        }
        return InferenceResult(
            provider="stepfun",
            model_name=self.settings.stepfun_model,
            overall_pass=required_codes <= detected_codes,
            summary=f"Step 5 已完成 {len(model_responses)} 组视觉核对",
            findings=findings,
            raw_response={
                "mode": "rustfs_base64_frames",
                "frame_asset_keys": frame_assets,
                "sampled_timestamps": [timestamp for timestamp, _ in frames],
                "analysis_windows": [
                    {
                        "start_seconds": window[0][0],
                        "end_seconds": window[-1][0],
                        "frame_timestamps": [timestamp for timestamp, _ in window],
                    }
                    for window in windows
                ],
                "model_responses": model_responses,
            },
        )

    def _analysis_windows(self, frames: list[tuple[int, bytes]]) -> list[list[tuple[int, bytes]]]:
        if not frames:
            return []
        window_seconds = max(2, int(getattr(self.settings, "stepfun_analysis_window_seconds", 20)))
        overlap_seconds = max(
            0,
            min(
                window_seconds - 1,
                int(getattr(self.settings, "stepfun_analysis_window_overlap_seconds", 4)),
            ),
        )
        max_images = 50  # Keep a margin below Step 5's 60-image request limit.
        timestamps = [timestamp for timestamp, _ in frames]
        by_timestamp = dict(frames)
        duration = timestamps[-1]
        step = max(1, window_seconds - overlap_seconds)
        starts = list(range(0, duration + 1, step)) or [0]
        windows: list[list[tuple[int, bytes]]] = []
        for start in starts:
            end = min(duration, start + window_seconds)
            selected = [
                (timestamp, by_timestamp[timestamp])
                for timestamp in timestamps
                if start <= timestamp <= end
            ]
            if not selected:
                continue
            if len(selected) > max_images:
                stride = (len(selected) - 1) / (max_images - 1)
                selected = [selected[round(index * stride)] for index in range(max_images)]
            windows.append(selected)
            if end >= duration:
                break
        return windows

    def _chat_payload(
        self,
        steps: list[SopStepLike],
        content: list[dict],
        available_timestamps: list[int] | None = None,
    ) -> dict:
        timestamp_items: dict = {"type": "integer"}
        if available_timestamps:
            timestamp_items["enum"] = available_timestamps
        finding_fields = {
            "step_code": {"type": "string", "enum": [step.code for step in steps]},
            "detected": {"type": "boolean"},
            "confidence": {
                "type": "integer",
                "description": "对 detected 判断的确信程度，0 表示无法判断，清晰证据为 80-100",
            },
            # Time ranges are derived by FlowGuard from selected evidence
            # frames. The model must not invent a start or end second.
            "start_seconds": {"type": "null"},
            "end_seconds": {"type": "null"},
            "evidence": {"type": "string"},
            "frame_timestamps": {
                "type": "array",
                "items": timestamp_items,
                "maxItems": 6,
            },
            "occluded": {"type": "boolean"},
            "evidence_score": {
                "type": "integer",
                "description": "直接视觉证据的强度，未见或看不清为 0-40，清晰可见为 80-100",
            },
        }
        return {
            "model": self.settings.stepfun_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是工业装配审计员。只根据给出的视觉证据判断，禁止补全未看到的动作。"
                        "start_seconds 和 end_seconds 必须填 null；时间区间由服务端根据真实帧计算。"
                    ),
                },
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "sop_video_findings",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "summary": {"type": "string"},
                            "findings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": finding_fields,
                                    "required": list(finding_fields),
                                },
                            },
                        },
                        "required": ["summary", "findings"],
                    },
                },
            },
            "reasoning_effort": "low",
            "max_tokens": 8192,
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
            "每个步骤只能选择最直接支持该步骤的真实帧，不能因为后续成品状态而回填前置步骤；"
            "只有正在执行该步骤的动作才算 detected=true，已经安装完成后的静态部件、手停留在部件旁、"
            "或后续画面中看到的最终状态都不能反推前置步骤；"
            "对于多个同类步骤（例如第一个至第六个风扇），优先依据动作首次发生的时间顺序判断；"
            "若只看到同类装配动作但无法区分具体序号，detected 必须为 false，"
            "但必须保留实际看到动作的帧；"
            "confidence 表示对 detected 判断的确信程度，不是动作出现概率；"
            "确认未出现且画面覆盖充分时也可高分，遮挡或抽帧证据不足时应低分。"
            "detected=false 不代表 confidence=0；仅完全无法判断时填 0。"
            "清晰看见动作时 confidence 和 evidence_score 应为 80-100，"
            "不能把明确观察到的动作标记为 0 分。"
            f"\nSOP：{json.dumps(step_payload, ensure_ascii=False)}"
            f"\n可用时间戳：{timestamps}"
            "\n按照指定 JSON Schema 输出 summary 和 findings，每个 SOP 步骤必须且只能出现一次。"
            "每项 evidence 不超过 40 字，frame_timestamps 只能使用给定的秒数，"
            "最多选择 6 张相邻证据帧；"
            "start_seconds 和 end_seconds 必须为 null。"
        )

    @staticmethod
    def _compact_prompt(
        steps: list[SopStepLike], available_timestamps: list[int] | None = None
    ) -> str:
        names = [{"step_code": step.code, "name": step.name} for step in steps]
        available = available_timestamps or []
        return (
            "逐项核对视频帧中的动作，只根据画面判断，不要推测。"
            f"步骤：{json.dumps(names, ensure_ascii=False)}。"
            f"可用真实时间戳：{available}。"
            "只输出 JSON 对象，必须有 findings 数组，每个步骤一项；"
            "每项包含 step_code、detected、confidence、start_seconds、end_seconds、"
            "evidence、frame_timestamps、occluded、evidence_score。"
            "start_seconds 和 end_seconds 必须为 null，"
            "frame_timestamps 只能从可用真实时间戳中选择，最多 6 张；"
            "看不清或未出现则 detected=false；证据文字不超过 40 字。"
            "请为每一步独立填写 0-100 的 confidence 和 evidence_score；"
            "清晰看到动作时两项应为 80-100，只有完全无法判断时 confidence 才为 0。"
        )

    @staticmethod
    def _has_usable_findings(payload: dict, steps: list[SopStepLike]) -> bool:
        findings = payload.get("findings")
        codes = {step.code for step in steps}
        return isinstance(findings, list) and any(
            isinstance(item, dict) and item.get("step_code") in codes for item in findings
        )

    @classmethod
    def _needs_retry(cls, payload: dict, steps: list[SopStepLike]) -> bool:
        if not cls._has_usable_findings(payload, steps):
            return True
        findings = payload["findings"]
        codes = {step.code for step in steps}
        returned = [
            item for item in findings if isinstance(item, dict) and item.get("step_code") in codes
        ]
        if {item["step_code"] for item in returned} != codes:
            return True
        return all(_coerce_int(item.get("confidence"), 0) == 0 for item in returned)

    def _parse(
        self,
        payload: dict,
        steps: list[SopStepLike],
        available_timestamps: list[int] | None = None,
        raw_response: dict | None = None,
    ) -> InferenceResult:
        if not self._has_usable_findings(payload, steps):
            raise VideoInferenceError("Step 5 未返回可用的步骤判断")
        by_code = {
            item.get("step_code"): item
            for item in (payload.get("findings") or [])
            if isinstance(item, dict)
        }
        allowed_timestamps = set(available_timestamps or [])
        findings = []
        for step in steps:
            item = by_code.get(step.code)
            if not isinstance(item, dict):
                findings.append(
                    InferenceFinding(
                        step_code=step.code,
                        detected=False,
                        confidence=0,
                        start_seconds=None,
                        end_seconds=None,
                        evidence="Step 5 未返回该步骤的视觉判断，需要人工复核",
                        frame_timestamps=[],
                        evidence_score=0,
                        candidate_frame_timestamps=[],
                    )
                )
                continue
            detected = bool(item.get("detected"))
            model_timestamps = sorted(
                {
                    value
                    for value in (_as_int(raw) for raw in (item.get("frame_timestamps") or []))
                    if value is not None
                }
            )
            if available_timestamps is not None:
                evidence_timestamps = [
                    value for value in model_timestamps if value in allowed_timestamps
                ]
                # Accept legacy responses only when their claimed range lands
                # exactly on a real sampled frame. Arbitrary model seconds are
                # never used as a cut boundary.
                if not evidence_timestamps:
                    evidence_timestamps = sorted(
                        {
                            value
                            for value in (
                                _as_int(item.get("start_seconds")),
                                _as_int(item.get("end_seconds")),
                            )
                            if value is not None and value in allowed_timestamps
                        }
                    )
            else:
                evidence_timestamps = model_timestamps or sorted(
                    {
                        value
                        for value in (
                            _as_int(item.get("start_seconds")),
                            _as_int(item.get("end_seconds")),
                        )
                        if value is not None
                    }
                )
            candidate_timestamps = evidence_timestamps
            start_seconds = min(evidence_timestamps) if detected and evidence_timestamps else None
            end_seconds = max(evidence_timestamps) if detected and evidence_timestamps else None
            findings.append(
                InferenceFinding(
                    step_code=step.code,
                    detected=detected,
                    confidence=max(0, min(100, _coerce_int(item.get("confidence"), 0))),
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    evidence=str(item.get("evidence") or ""),
                    frame_timestamps=evidence_timestamps,
                    occluded=bool(item.get("occluded", False)),
                    evidence_score=max(
                        0,
                        min(
                            100,
                            _coerce_int(item.get("evidence_score", item.get("confidence")), 0),
                        ),
                    ),
                    chunk_idx=_as_int(item.get("chunk_idx")),
                    cv_boundary_score=_as_float(item.get("cv_boundary_score")),
                    candidate_frame_timestamps=candidate_timestamps,
                    candidate_start_seconds=(
                        min(candidate_timestamps) if candidate_timestamps else None
                    ),
                    candidate_end_seconds=(
                        max(candidate_timestamps) if candidate_timestamps else None
                    ),
                )
            )
        overall_pass = all(item.detected and item.start_seconds is not None for item in findings)
        return InferenceResult(
            provider="stepfun",
            model_name=self.settings.stepfun_model,
            overall_pass=overall_pass,
            summary=str(payload.get("summary", "Step 5 视频检测完成")),
            findings=findings,
            raw_response=raw_response or payload,
        )

    @staticmethod
    def _finding_rank(finding: InferenceFinding) -> tuple[int, int, int, int]:
        timestamps = finding.frame_timestamps or finding.candidate_frame_timestamps or []
        first_timestamp = min(timestamps) if timestamps else 10**9
        if finding.detected and finding.start_seconds is not None:
            # Among confirmed observations, prefer the earliest real action;
            # this prevents a later static-state match from winning on score.
            return (
                1,
                10**9 - finding.start_seconds,
                (
                    finding.evidence_score
                    if finding.evidence_score is not None
                    else finding.confidence
                ),
                finding.confidence,
            )
        return (
            0,
            finding.evidence_score if finding.evidence_score is not None else finding.confidence,
            finding.confidence,
            -first_timestamp,
        )

    @staticmethod
    def _candidate_time_range(finding: InferenceFinding) -> tuple[int, int] | None:
        timestamps = finding.candidate_frame_timestamps or finding.frame_timestamps
        if not timestamps:
            return None
        return min(timestamps), max(timestamps)

    @staticmethod
    def _has_direct_evidence(finding: InferenceFinding) -> bool:
        return bool(
            finding.detected
            and finding.start_seconds is not None
            and finding.end_seconds is not None
            and finding.frame_timestamps
        )

    @staticmethod
    def _is_action_candidate(finding: InferenceFinding) -> bool:
        """Return true only for an uncertain finding that describes an action.

        Step 5 often returns the sampled frames even when it cannot map a
        generic action to a repeated SOP step. Those frames are valuable for
        review, but negative observations such as "未见安装动作" must never
        become a candidate just because the model supplied timestamps.
        """
        if finding.detected or Step5InferenceAdapter._candidate_time_range(finding) is None:
            return False
        evidence = finding.evidence.strip()
        if not evidence:
            return False
        action_markers = (
            "有装配动作",
            "可见手部装配",
            "装配操作",
            "安装动作",
            "风扇安装动作",
            "电源安装动作",
            "按压",
            "推入",
            "放入",
            "连接",
        )
        negative_markers = (
            "未观察到",
            "未见",
            "未显示",
            "未出现",
            "没有观察到",
            "无安装",
        )
        return any(marker in evidence for marker in action_markers) and not any(
            marker in evidence for marker in negative_markers
        )

    @staticmethod
    def _downgrade_candidate(finding: InferenceFinding) -> InferenceFinding:
        """Keep an early action location without presenting it as confirmed."""
        score = min(finding.evidence_score or finding.confidence, 59)
        confidence = min(finding.confidence, 59)
        evidence = finding.evidence
        if "待复核" not in evidence:
            evidence = f"{evidence}；动作位置为候选证据，步骤序号待复核"
        return InferenceFinding(
            step_code=finding.step_code,
            detected=False,
            confidence=confidence,
            start_seconds=None,
            end_seconds=None,
            evidence=evidence,
            frame_timestamps=[],
            occluded=finding.occluded,
            evidence_score=score,
            chunk_idx=finding.chunk_idx,
            cv_boundary_score=finding.cv_boundary_score,
            candidate_frame_timestamps=(
                finding.candidate_frame_timestamps or finding.frame_timestamps
            ),
            candidate_start_seconds=finding.candidate_start_seconds
            or (Step5InferenceAdapter._candidate_time_range(finding) or (None, None))[0],
            candidate_end_seconds=finding.candidate_end_seconds
            or (Step5InferenceAdapter._candidate_time_range(finding) or (None, None))[1],
        )

    @classmethod
    def _merge_window_findings(
        cls, findings: list[InferenceFinding], steps: list[SopStepLike]
    ) -> list[InferenceFinding]:
        """Select one observation per step while retaining uncertain candidates.

        The provider is called on overlapping windows. A later window can
        describe an already-installed component with high confidence and
        incorrectly assign it to an earlier repeated step. For the first
        required step, an earlier explicit action candidate is therefore more
        useful than a later confirmation: it preserves the real location and
        sends the ambiguity to human review instead of moving the step to a
        false late timestamp. Other steps retain the existing conservative
        confirmed-evidence ranking until an equivalent ordered candidate is
        available.
        """
        grouped: dict[str, list[InferenceFinding]] = {}
        for finding in findings:
            grouped.setdefault(finding.step_code, []).append(finding)
        selected_by_code: dict[str, InferenceFinding] = {}
        required_steps = sorted(
            (step for step in steps if getattr(step, "required", True)),
            key=lambda item: item.sequence,
        )
        first_required_code = required_steps[0].code if required_steps else None
        cursor: int | None = None
        for step in sorted(steps, key=lambda item: item.sequence):
            options = grouped.get(step.code, [])
            if not options:
                selected_by_code[step.code] = InferenceFinding(
                    step_code=step.code,
                    detected=False,
                    confidence=0,
                    start_seconds=None,
                    end_seconds=None,
                    evidence="Step 5 未返回该步骤的视觉判断，需要人工复核",
                    frame_timestamps=[],
                    evidence_score=0,
                    candidate_frame_timestamps=[],
                )
                continue
            selected: InferenceFinding | None = None
            rank_options = options
            if getattr(step, "required", True) and cursor is not None:
                ordered_direct_options = [
                    option
                    for option in options
                    if cls._has_direct_evidence(option)
                    and option.start_seconds is not None
                    and option.start_seconds >= cursor
                ]
                if ordered_direct_options:
                    rank_options = ordered_direct_options
            if step.code == first_required_code:
                direct_options = [option for option in options if cls._has_direct_evidence(option)]
                action_candidates = [
                    option for option in options if cls._is_action_candidate(option)
                ]
                if direct_options and action_candidates:
                    earliest_direct = min(
                        direct_options,
                        key=lambda option: option.start_seconds
                        if option.start_seconds is not None
                        else float("inf"),
                    )
                    earliest_candidate = min(
                        action_candidates,
                        key=lambda option: cls._candidate_time_range(option)[0]
                        if cls._candidate_time_range(option) is not None
                        else float("inf"),
                    )
                    candidate_range = cls._candidate_time_range(earliest_candidate)
                    if (
                        candidate_range is not None
                        and earliest_direct.start_seconds is not None
                        and candidate_range[0] < earliest_direct.start_seconds
                    ):
                        selected = cls._downgrade_candidate(earliest_candidate)
            if selected is None:
                selected = max(rank_options, key=cls._finding_rank)
            selected_by_code[step.code] = selected
            if getattr(step, "required", True):
                selected_range = (
                    (selected.start_seconds, selected.end_seconds)
                    if cls._has_direct_evidence(selected)
                    else cls._candidate_time_range(selected)
                )
                if selected_range is not None:
                    cursor = selected_range[1] if cursor is None else max(cursor, selected_range[1])
        return [selected_by_code[step.code] for step in steps]

    @staticmethod
    def _enforce_temporal_order(
        findings: list[InferenceFinding], steps: list[SopStepLike]
    ) -> list[InferenceFinding]:
        """Reject overlapping evidence instead of fabricating a sorted cut list."""
        by_code = {finding.step_code: finding for finding in findings}
        cursor: int | None = None
        for step in sorted(steps, key=lambda item: item.sequence):
            if not getattr(step, "required", True):
                continue
            finding = by_code.get(step.code)
            if finding is None or not finding.detected or finding.start_seconds is None:
                continue
            if cursor is not None and finding.start_seconds < cursor:
                by_code[step.code] = InferenceFinding(
                    step_code=finding.step_code,
                    detected=finding.detected,
                    confidence=finding.confidence,
                    start_seconds=None,
                    end_seconds=None,
                    evidence=(
                        f"{finding.evidence}；时间证据与前置步骤重叠，需要人工复核"
                    ).strip("；"),
                    frame_timestamps=[],
                    occluded=True,
                    evidence_score=min(finding.evidence_score or finding.confidence, 40),
                    chunk_idx=finding.chunk_idx,
                    cv_boundary_score=finding.cv_boundary_score,
                    candidate_frame_timestamps=(
                        finding.candidate_frame_timestamps or finding.frame_timestamps
                    ),
                    candidate_start_seconds=finding.candidate_start_seconds
                    or finding.start_seconds,
                    candidate_end_seconds=finding.candidate_end_seconds or finding.end_seconds,
                )
                continue
            current_end = finding.end_seconds or finding.start_seconds
            cursor = current_end if cursor is None else max(cursor, current_end)
        return [by_code.get(finding.step_code, finding) for finding in findings]


class DeepStreamInferenceAdapter:
    """Thin client for NVIDIA's unchanged DeepStream SOP microservice.

    DeepStream owns GEBD/chunk boundaries. FlowGuard intentionally maps its
    chunk metadata into our provider-neutral finding contract and performs the
    final execution-graph decision outside the NVIDIA service.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze(self, filename: str, video: bytes, steps: list[SopStepLike]) -> InferenceResult:
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
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                    f'filename="{Path(filename).name}"\r\nContent-Type: {mime}\r\n\r\n'
                ).encode(),
                video,
                (
                    f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="purpose"'
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
                            text or f"DeepStream 在 chunk {chunk.get('chunk_idx')} 中观察到该步骤"
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
