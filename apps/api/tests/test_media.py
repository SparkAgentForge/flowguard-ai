from io import BytesIO
from unittest.mock import Mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from flowguard_api.infrastructure.storage.providers import LocalFileStorage, S3FileStorage
from flowguard_api.routes.media import media_response


def test_private_storage_playback_and_seeking(tmp_path):
    storage = LocalFileStorage(str(tmp_path))
    storage.put("preview.mp4", b"0123456789")
    app = FastAPI()

    @app.get("/video")
    def video(request: Request):
        return media_response(storage, "preview.mp4", request)

    with TestClient(app) as client:
        whole = client.get("/video")
        assert whole.status_code == 200
        assert whole.content == b"0123456789"
        assert "location" not in whole.headers
        assert whole.headers["accept-ranges"] == "bytes"
        for value, expected, content_range in [
            ("bytes=2-5", b"2345", "bytes 2-5/10"),
            ("bytes=8-", b"89", "bytes 8-9/10"),
            ("bytes=-3", b"789", "bytes 7-9/10"),
            ("bytes=8-999", b"89", "bytes 8-9/10"),
        ]:
            response = client.get("/video", headers={"Range": value})
            assert response.status_code == 206
            assert response.content == expected
            assert response.headers["content-range"] == content_range
            assert int(response.headers["content-length"]) == len(expected)
        for value in ["bytes=10-", "bytes=8-2", "bytes=-0", "bytes=-", "bytes=0-1,3-4"]:
            response = client.get("/video", headers={"Range": value})
            assert response.status_code == 416
            assert response.headers["content-range"] == "bytes */10"
        storage.delete("preview.mp4")
        assert client.get("/video").status_code == 404


def test_s3_stream_uses_internal_client_and_closes_body():
    storage = object.__new__(S3FileStorage)
    storage._bucket_ready = True
    storage.bucket = "private-evidence"
    storage._client = Mock()
    storage._public_client = Mock()
    body = BytesIO(b"2345")
    storage._client.head_object.return_value = {"ContentLength": 10}
    storage._client.get_object.return_value = {"Body": body}
    storage._client_error = RuntimeError
    app = FastAPI()

    @app.get("/video")
    def video(request: Request):
        return media_response(storage, "private.mp4", request)

    with TestClient(app) as client:
        response = client.get("/video", headers={"Range": "bytes=2-5"})
        assert response.status_code == 206
        assert response.content == b"2345"
    assert body.closed
    storage._client.get_object.assert_called_once_with(
        Bucket="private-evidence", Key="private.mp4", Range="bytes=2-5"
    )
    storage._public_client.generate_presigned_url.assert_not_called()
