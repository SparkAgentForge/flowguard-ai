"""Small Step 5-compatible multimodal chat client shared by adapters."""

import json
import urllib.error
import urllib.request
from collections.abc import Sequence

from flowguard_api.config import Settings, get_settings
from flowguard_api.core.inference import VideoInferenceError


class Step5VisionClient:
    """Call Step 5's OpenAI-compatible multimodal chat endpoint."""

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
        except (urllib.error.URLError, json.JSONDecodeError, TypeError, TimeoutError) as error:
            raise VideoInferenceError("Step 5 请求失败或返回内容无法解析") from error

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
