"""Small Step 5-compatible multimodal chat client shared by adapters."""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from flowguard_api.config import Settings, get_settings
from flowguard_api.core.inference import VideoInferenceError


class Step5VisionClient:
    """Call Step 5's OpenAI-compatible multimodal chat endpoint."""

    _MAX_ERROR_DETAIL_LENGTH = 240

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def chat(self, content: Sequence[dict], system_prompt: str) -> dict:
        if not self.settings.stepfun_api_key:
            raise VideoInferenceError("未配置 FLOWGUARD_STEPFUN_API_KEY")
        payload = {
            "model": self.settings.stepfun_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": list(content)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        return self.post_json(
            f"{self.settings.stepfun_base_url.rstrip('/')}/chat/completions", payload
        )

    def post_json(self, url: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Authorization": f"Bearer {self.settings.stepfun_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.settings.stepfun_timeout_seconds
            ) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = self._http_error_detail(error)
            suffix = f"：{detail}" if detail else ""
            raise VideoInferenceError(f"Step 5 返回 HTTP {error.code}{suffix}") from error
        except TimeoutError as error:
            raise VideoInferenceError("Step 5 请求超时") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise VideoInferenceError("Step 5 请求超时") from error
            raise VideoInferenceError("Step 5 网络请求失败") from error
        except (json.JSONDecodeError, TypeError) as error:
            raise VideoInferenceError("Step 5 返回内容无法解析") from error

    def _http_error_detail(self, error: urllib.error.HTTPError) -> str:
        """Extract a short, credential-free diagnostic from an HTTP error body."""
        try:
            raw_body = error.read(8192)
        except (AttributeError, OSError, ValueError):
            return ""
        if not raw_body:
            return ""
        raw_text = (
            raw_body.decode("utf-8", errors="replace")
            if isinstance(raw_body, bytes)
            else str(raw_body)
        )
        try:
            body: Any = json.loads(raw_text)
        except json.JSONDecodeError:
            body = None

        detail = self._json_error_detail(body) if body is not None else ""
        if not detail:
            detail = raw_text
        detail = re.sub(r"\s+", " ", detail).strip()
        detail = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", detail)
        if self.settings.stepfun_api_key:
            detail = detail.replace(self.settings.stepfun_api_key, "[REDACTED]")
        return detail[: self._MAX_ERROR_DETAIL_LENGTH]

    @classmethod
    def _json_error_detail(cls, body: Any) -> str:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                for key in ("message", "detail", "code"):
                    value = error.get(key)
                    if isinstance(value, (str, int, float)) and str(value).strip():
                        return str(value)
            for key in ("message", "detail", "error"):
                value = body.get(key)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    return str(value)
        return ""

    @staticmethod
    def response_payload(raw_api_response: dict) -> dict:
        try:
            message = raw_api_response["choices"][0]["message"]["content"]
            if isinstance(message, dict):
                return message
            text = str(message).strip()
            if text.startswith("```"):
                text = text.strip("`").removeprefix("json").strip()
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise TypeError("Step 5 返回的 JSON 根节点不是对象")
            return payload
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as error:
            raise VideoInferenceError("Step 5 返回内容无法解析") from error
