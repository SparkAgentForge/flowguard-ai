import base64
import io
from urllib.error import HTTPError

import pytest

from flowguard_api.config import Settings
from flowguard_api.core.inference import VideoInferenceError
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient

TEST_DATABASE_URL = "postgresql+pg8000://test:test@localhost:5432/flowguard_test"


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
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
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
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
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
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="请求超时"):
        client.post_json("https://example.test/chat/completions", {"messages": []})


def test_step5_client_handles_http_error_without_response_body(monkeypatch) -> None:
    error = HTTPError("https://example.test", 503, "unavailable", None, None)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = Step5VisionClient(
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="Step 5 返回 HTTP 503"):
        client.post_json("https://example.test/chat/completions", {"messages": []})


def test_step5_image_part_uses_data_url() -> None:
    part = Step5VisionClient.image_part(b"test-image", "image/jpeg")
    assert part == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(b"test-image").decode("ascii")
        },
    }


def test_step5_http_error_does_not_echo_inline_image(monkeypatch) -> None:
    image_url = "data:image/jpeg;base64," + "A" * 300
    error = HTTPError(
        "https://example.test",
        400,
        "bad request",
        None,
        io.BytesIO(f"invalid image: {image_url}".encode()),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error)
    )
    client = Step5VisionClient(
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="REDACTED IMAGE") as raised:
        client.post_json("https://example.test/chat/completions", {"messages": []})
    assert "data:image" not in str(raised.value)


def test_step5_reports_oversized_inline_image_request(monkeypatch) -> None:
    error = HTTPError("https://example.test", 413, "too large", None, None)
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error)
    )
    client = Step5VisionClient(
        Settings(database_url=TEST_DATABASE_URL, stepfun_api_key="test-key", _env_file=None)
    )

    with pytest.raises(VideoInferenceError, match="图片请求过大"):
        client.post_json("https://example.test/chat/completions", {"messages": []})
