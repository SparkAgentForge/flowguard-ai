"""Generate small, browser-playable evidence clips from an audit video."""

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from flowguard_api.config import get_settings
from flowguard_api.core.media import is_media_tool_runtime_error, resolve_media_tool
from flowguard_api.core.storage import FileStorage
from flowguard_api.models import AuditFinding, VideoAsset


class EvidenceClipError(RuntimeError):
    pass


def _range_for(finding: AuditFinding, kind: str) -> tuple[int, int] | None:
    if kind == "confirmed":
        start, end = finding.start_seconds, finding.end_seconds
    else:
        start, end = finding.candidate_start_seconds, finding.candidate_end_seconds
    if start is None or end is None:
        return None
    return max(0, int(start) - 2), max(int(start) + 1, int(end) + 2)


def _clip_key(video: VideoAsset, audit_id: str, finding: AuditFinding, kind: str) -> str:
    return (
        f"evidence-clips/{video.work_order_id}/{audit_id}/"
        f"{finding.sequence:03d}-{finding.sop_step_id}-{kind}.mp4"
    )


def _make_clip(source: bytes, filename: str, start: int, end: int) -> bytes:
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="flowguard-evidence-clip-") as directory:
        root = Path(directory)
        source_path = root / (Path(filename).name or "source.mp4")
        target_path = root / "clip.mp4"
        source_path.write_bytes(source)
        try:
            ffmpeg = resolve_media_tool(settings.ffmpeg_binary, "ffmpeg")
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    str(start),
                    "-i",
                    str(source_path),
                    "-t",
                    str(max(1, end - start)),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "26",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(target_path),
                ],
                check=True,
                capture_output=True,
                timeout=600,
            )
        except FileNotFoundError as error:
            raise EvidenceClipError("服务器未安装 ffmpeg，无法生成证据片段") from error
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.CalledProcessError) and is_media_tool_runtime_error(
                error
            ):
                raise EvidenceClipError("FFmpeg 安装不完整，无法生成证据片段") from error
            raise EvidenceClipError("视频无法切割为可播放的证据片段") from error
        if not target_path.is_file():
            raise EvidenceClipError("FFmpeg 未生成证据片段")
        return target_path.read_bytes()


def generate_evidence_clips(
    storage: FileStorage,
    video: VideoAsset,
    audit_id: str,
    findings: list[AuditFinding],
) -> dict[str, str]:
    """Create confirmed/candidate clips and return their object keys."""
    try:
        source = storage.get(video.storage_key)
    except Exception as error:
        raise EvidenceClipError("无法读取原始视频，证据片段未生成") from error
    clips: dict[str, str] = {}
    for finding in findings:
        kinds = ["confirmed"] if finding.start_seconds is not None else []
        if finding.candidate_start_seconds is not None:
            kinds.append("candidate")
        for kind in kinds:
            time_range = _range_for(finding, kind)
            if time_range is None:
                continue
            key = _clip_key(video, audit_id, finding, kind)
            try:
                if not storage.exists(key):
                    storage.put(key, _make_clip(source, video.filename, *time_range))
            except EvidenceClipError:
                raise
            except Exception as error:
                raise EvidenceClipError("证据片段写入对象存储失败") from error
            clips[f"{finding.sop_step_id}:{kind}"] = key
    return clips


def evidence_clip_key(
    raw_response: dict[str, Any], sop_step_id: str, kind: str
) -> str | None:
    clips = raw_response.get("evidence_clips", {}) if isinstance(raw_response, dict) else {}
    value = clips.get(f"{sop_step_id}:{kind}") if isinstance(clips, dict) else None
    return value if isinstance(value, str) else None
