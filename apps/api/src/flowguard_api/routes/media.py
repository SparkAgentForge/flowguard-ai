"""Same-origin media delivery, including seeking with private object storage."""

import re

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from flowguard_api.core.storage import FileStorage


def media_response(storage: FileStorage, key: str, request: Request) -> Response:
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="视频文件不存在")
    size = storage.size(key)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-cache"}
    start, end = 0, size - 1
    range_header = request.headers.get("range")
    partial = False
    # No validator is advertised: ignore conditional ranges and return the full
    # representation instead of claiming that an unknown validator matched.
    if range_header and not request.headers.get("if-range"):
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        try:
            if not match or not any(match.groups()) or not size:
                raise ValueError
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                if suffix <= 0:
                    raise ValueError
                start = max(size - suffix, 0)
            if start > end or start >= size:
                raise ValueError
        except ValueError:
            return Response(
                status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"}
            )
        partial = True
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    length = end - start + 1
    headers["Content-Length"] = str(length)
    if not length:
        return Response(content=b"", media_type="video/mp4", headers=headers)
    stream = storage.open_range(key, start, end)

    def chunks():
        remaining = length
        try:
            while remaining:
                chunk = stream.read(min(256 * 1024, remaining))
                if not chunk:
                    raise OSError("视频读取中断")
                remaining -= len(chunk)
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        chunks(), status_code=206 if partial else 200, media_type="video/mp4",
        headers=headers, background=BackgroundTask(stream.close),
    )
