import io
from urllib.error import HTTPError

import pytest

from flowguard_api.config import Settings
from flowguard_api.core.inference import VideoInferenceError
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient


def test_step5_client_reports_http_json_detail_without_credentials(monkeypatch) -> None:
    error = HTTPError(
        "https://example.test",
        400,
        "bad request",
        {"Content-Type": "application/json"},
        io.BytesIO(
            b'{"error":{"message":"too many images", "code":"image_limit"}}'
        ),
    )

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = Step5VisionClient(
        Settings(database_url="sqlite://", stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError) as raised:
        client.post_json("https://example.test/chat/completions", {"messages": []})
    assert str(raised.value) == "Step 5 返回 HTTP 400：too many images"
    assert "test-key" not in str(raised.value)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"plain text upstream failure", "plain text upstream failure"),
        (b"x" * 500, "x" * 240),
    ],
)
def test_step5_client_reports_truncated_non_json_detail(monkeypatch, body, message) -> None:
    error = HTTPError(
        "https://example.test", 429, "rate limited", None, io.BytesIO(body)
    )
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = Step5VisionClient(
        Settings(database_url="sqlite://", stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="HTTP 429") as raised:
        client.post_json("https://example.test/chat/completions", {"messages": []})
    assert message in str(raised.value)


def test_step5_client_reports_safe_error_category(monkeypatch) -> None:
    error = TimeoutError("timed out")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = Step5VisionClient(
        Settings(database_url="sqlite://", stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="请求超时"):
        client.post_json("https://example.test/chat/completions", {"messages": []})


def test_step5_client_handles_http_error_without_response_body(monkeypatch) -> None:
    error = HTTPError("https://example.test", 503, "unavailable", None, None)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = Step5VisionClient(
        Settings(database_url="sqlite://", stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="Step 5 返回 HTTP 503"):
        client.post_json("https://example.test/chat/completions", {"messages": []})
