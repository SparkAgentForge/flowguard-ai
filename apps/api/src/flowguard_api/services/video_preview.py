"""Create a browser-compatible, cached preview of an uploaded audit video."""

import subprocess
import tempfile
from pathlib import Path

from flowguard_api.config import get_settings
from flowguard_api.core.media import is_media_tool_runtime_error, resolve_media_tool
from flowguard_api.core.storage import FileStorage
from flowguard_api.models import VideoAsset


class VideoPreviewError(RuntimeError):
    pass


def ensure_browser_preview(storage: FileStorage, video: VideoAsset) -> str:
    preview_key = f"video-previews/{video.id}.mp4"
    if storage.exists(preview_key):
        return preview_key

    with tempfile.TemporaryDirectory(prefix="flowguard-preview-") as directory:
        source = Path(directory) / f"source{Path(video.filename).suffix.lower()}"
        target = Path(directory) / "preview.mp4"
        source.write_bytes(storage.get(video.storage_key))
        try:
            ffmpeg = resolve_media_tool(get_settings().ffmpeg_binary, "ffmpeg")
            subprocess.run(
                [
                    ffmpeg, "-v", "error", "-y", "-i", str(source),
                    "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", "scale='min(960,iw)':-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(target),
                ],
                check=True,
                capture_output=True,
                timeout=600,
            )
        except FileNotFoundError as error:
            raise VideoPreviewError("服务器未安装 ffmpeg，无法生成浏览器预览") from error
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.CalledProcessError) and is_media_tool_runtime_error(
                error
            ):
                raise VideoPreviewError("FFmpeg 安装不完整，无法生成浏览器预览") from error
            raise VideoPreviewError("视频无法转换为浏览器可播放格式") from error
        storage.put(preview_key, target.read_bytes())
    return preview_key
