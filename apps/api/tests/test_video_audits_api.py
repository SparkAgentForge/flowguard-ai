import subprocess
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.core.inference import VideoInferenceError
from flowguard_api.infrastructure.storage import LocalFileStorage, get_file_storage
from flowguard_api.models import Sop, SopStatus, SopStep, SopVersion, VideoAsset
from flowguard_api.services.video_preview import ensure_browser_preview


def seed_published_work_order(session: Session, code: str = "WO-VIDEO-001") -> str:
    sop = Sop(code=f"SOP-{code}", name="装配 SOP", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    session.add_all(
        [
            SopStep(
                sop_version_id=version.id,
                code="scan_part",
                sequence=1,
                name="扫描零件",
                evidence_requirements=["出现扫码动作"],
            ),
            SopStep(
                sop_version_id=version.id,
                code="install_seal",
                sequence=2,
                name="安装密封圈",
                evidence_requirements=["密封圈完全进入槽位"],
            ),
        ]
    )
    from flowguard_api.models import WorkOrder

    work_order = WorkOrder(code=code, product_code="PUMP-A01", sop_version_id=version.id)
    session.add(work_order)
    session.commit()
    return work_order.id


def test_upload_and_inspect_video_creates_findings(
    client: TestClient, session: Session, tmp_path, monkeypatch
) -> None:
    client.app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(str(tmp_path))
    work_order_id = seed_published_work_order(session)
    uploaded = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": ("assembly.mp4", BytesIO(b"demo-video"), "video/mp4")},
    )
    assert uploaded.status_code == 201
    video_id = uploaded.json()["id"]

    inspected = client.post(
        f"/api/v1/work-orders/{work_order_id}/inspect",
        json={"videoId": video_id, "actorId": "operator-01"},
    )

    assert inspected.status_code == 201
    body = inspected.json()
    assert body["status"] == "COMPLETED"
    assert len(body["findings"]) == 2
    assert body["findings"][1]["detected"] is False

    detail = client.get(f"/api/v1/work-orders/{work_order_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "EXCEPTION_PENDING"

    listed = client.get("/api/v1/work-orders")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == work_order_id

    audits = client.get(f"/api/v1/work-orders/{work_order_id}/audits")
    assert audits.status_code == 200
    assert [audit["id"] for audit in audits.json()] == [body["id"]]

    videos = client.get(f"/api/v1/work-orders/{work_order_id}/videos")
    assert videos.status_code == 200
    assert [video["id"] for video in videos.json()] == [video_id]
    assert videos.json()[0]["reworkTaskId"] is None

    monkeypatch.setattr(
        "flowguard_api.routes.video_audits.ensure_browser_preview",
        lambda storage, video: video.storage_key,
    )
    playback = client.get(f"/api/v1/work-orders/{work_order_id}/videos/{video_id}/content")
    assert playback.status_code == 200
    assert playback.content == b"demo-video"
    assert playback.headers["content-type"].startswith("video/mp4")
    assert client.get(
        f"/api/v1/work-orders/{work_order_id}/videos/unknown/content"
    ).status_code == 404


def test_browser_preview_is_cached(tmp_path, monkeypatch) -> None:
    storage = LocalFileStorage(str(tmp_path))
    storage.put("videos/original.mp4", b"source")
    video = VideoAsset(
        id="preview-test", filename="original.mp4", storage_key="videos/original.mp4"
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"browser-mp4")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    key = ensure_browser_preview(storage, video)
    assert key == ensure_browser_preview(storage, video)
    assert storage.get(key) == b"browser-mp4"
    assert len(calls) == 1


def test_video_upload_rejects_unsupported_extension(
    client: TestClient, session: Session
) -> None:
    work_order_id = seed_published_work_order(session, "WO-VIDEO-002")
    response = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": ("assembly.txt", BytesIO(b"not-video"), "text/plain")},
    )
    assert response.status_code == 415


def test_published_sop_versions_are_listed(client: TestClient, session: Session) -> None:
    seed_published_work_order(session, "WO-VIDEO-003")
    response = client.get("/api/v1/sop-versions")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "PUBLISHED"


def test_occluded_audit_exposes_targeted_review_request(
    client: TestClient, session: Session
) -> None:
    work_order_id = seed_published_work_order(session, "WO-VIDEO-004")
    uploaded = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": ("occluded.mp4", BytesIO(b"demo-video"), "video/mp4")},
    )
    video_id = uploaded.json()["id"]
    inspected = client.post(
        f"/api/v1/work-orders/{work_order_id}/inspect",
        json={"videoId": video_id, "actorId": "operator-01"},
    )

    assert inspected.status_code == 201
    body = inspected.json()
    assert body["decision"] == "INSUFFICIENT_EVIDENCE"
    assert body["findings"][1]["evidenceStatus"] == "UNCERTAIN"
    assert body["findings"][1]["startSeconds"] is None
    assert body["findings"][1]["endSeconds"] is None
    assert body["findings"][1]["frameTimestamps"] == []
    assert body["reviewRequests"][0]["stepName"] == "安装密封圈"
    assert body["executionTrace"]["uncertainSteps"] == ["install_seal"]
    request_id = body["reviewRequests"][0]["id"]

    listed = client.get(
        f"/api/v1/work-orders/{work_order_id}/audits/{body['id']}/review-requests"
    )
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "PENDING"

    resolved = client.post(
        f"/api/v1/work-orders/{work_order_id}/audits/{body['id']}"
        f"/review-requests/{request_id}/resolve",
        json={"actorId": "reviewer-01", "decision": "CONFIRMED"},
    )
    assert resolved.status_code == 200
    assert resolved.json()[0]["status"] == "CONFIRMED"


def test_failed_inspection_releases_work_order_and_is_visible(
    client: TestClient, session: Session, monkeypatch, tmp_path
) -> None:
    client.app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(str(tmp_path))
    work_order_id = seed_published_work_order(session, "WO-VIDEO-005")
    uploaded = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": ("assembly.mp4", BytesIO(b"demo-video"), "video/mp4")},
    )
    video_id = uploaded.json()["id"]

    def fail_adapter(storage):
        class Adapter:
            def analyze(self, filename, video, steps):
                raise VideoInferenceError("Step 5 无法访问 RustFS 帧地址")

        return Adapter()

    monkeypatch.setattr(
        "flowguard_api.services.video_audit.get_video_inference_adapter", fail_adapter
    )
    inspected = client.post(
        f"/api/v1/work-orders/{work_order_id}/inspect",
        json={"videoId": video_id, "actorId": "operator-01"},
    )

    assert inspected.status_code == 422
    assert inspected.json()["detail"] == "Step 5 无法访问 RustFS 帧地址"
    detail = client.get(f"/api/v1/work-orders/{work_order_id}")
    assert detail.json()["status"] == "CREATED"
    audits = client.get(f"/api/v1/work-orders/{work_order_id}/audits")
    assert audits.status_code == 200
    assert audits.json()[0]["status"] == "FAILED"
