from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowguard_api.application import app
from flowguard_api.core.inference import VideoInferenceError
from flowguard_api.infrastructure.storage.factory import get_file_storage
from flowguard_api.models import Sop, SopStatus, SopStep, SopVersion, VideoAudit, WorkOrder


class MemoryStorage:
    def __init__(self) -> None:
        self.content: dict[str, bytes] = {}

    def put(self, key: str, content: bytes) -> None:
        self.content[key] = content

    def get(self, key: str) -> bytes:
        return self.content[key]


def seed_work_order(session: Session, code: str) -> str:
    sop = Sop(code=f"SOP-{code}", name="装配 SOP", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    session.add_all(
        [
            SopStep(sop_version_id=version.id, code="scan", sequence=1, name="扫描零件"),
            SopStep(sop_version_id=version.id, code="seal", sequence=2, name="安装密封圈"),
            SopStep(sop_version_id=version.id, code="cover", sequence=3, name="安装端盖"),
        ]
    )
    work_order = WorkOrder(code=code, product_code="PUMP-A01", sop_version_id=version.id)
    session.add(work_order)
    session.commit()
    return work_order.id


def upload_and_inspect(client: TestClient, work_order_id: str, filename: str) -> dict:
    uploaded = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": (filename, BytesIO(b"video"), "video/mp4")},
    )
    assert uploaded.status_code == 201
    inspected = client.post(
        f"/api/v1/work-orders/{work_order_id}/inspect",
        json={"videoId": uploaded.json()["id"], "actorId": "operator-01"},
    )
    assert inspected.status_code == 201
    return inspected.json()


def test_exception_rework_and_release_flow(
    client: TestClient, session: Session, monkeypatch
) -> None:
    storage = MemoryStorage()
    app.dependency_overrides[get_file_storage] = lambda: storage
    work_order_id = seed_work_order(session, "WO-WORKFLOW-001")

    audit = upload_and_inspect(client, work_order_id, "missing-step.mp4")
    assert audit["decision"] == "VIOLATION"

    exceptions = client.get("/api/v1/exceptions").json()
    exception_id = exceptions[0]["id"]
    confirmed = client.post(
        f"/api/v1/exceptions/{exception_id}/confirm",
        json={"actorId": "leader-01", "reason": "视频证据确认密封圈步骤缺失"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    assigned = client.post(
        f"/api/v1/exceptions/{exception_id}/rework-task",
        json={
            "actorId": "leader-01",
            "assigneeId": "operator-07",
            "instructions": "补装密封圈并重新拍摄完整装配视频",
        },
    )
    assert assigned.status_code == 201
    task_id = assigned.json()["reworkTask"]["id"]
    notifications = client.get("/api/v1/notifications?recipient_id=operator-07")
    assert notifications.status_code == 200
    assert notifications.json()[0]["reworkTaskId"] == task_id

    rework_video = client.post(
        f"/api/v1/rework-tasks/{task_id}/videos",
        files={"file": ("rework-normal.mp4", BytesIO(b"fixed"), "video/mp4")},
    )
    assert rework_video.status_code == 201
    persisted_video_id = rework_video.json()["id"]
    listed_videos = client.get(f"/api/v1/work-orders/{work_order_id}/videos")
    assert listed_videos.status_code == 200
    assert listed_videos.json()[0]["id"] == persisted_video_id
    refreshed_exception = client.get("/api/v1/exceptions").json()[0]
    assert refreshed_exception["status"] == "REWORK_SUBMITTED"
    direct_exception = client.get(f"/api/v1/exceptions/{exception_id}")
    assert direct_exception.status_code == 200
    assert direct_exception.json()["id"] == exception_id
    assert refreshed_exception["reworkTask"]["status"] == "SUBMITTED"
    from flowguard_api.routes import workflow
    original_execute = workflow.execute_video_audit

    def verify_durable_progress(db, order, video, file_storage, audit=None):
        with Session(session.bind) as observer:
            persisted = observer.get(VideoAudit, audit.id)
            assert persisted.status.value == "PROCESSING"
            assert observer.get(WorkOrder, order.id).status.value == "REWORK_REVIEW"
        duplicate = client.post(
            f"/api/v1/rework-tasks/{task_id}/review",
            json={"actorId": "quality-01", "videoId": persisted_video_id},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["audit"]["id"] == audit.id
        assert duplicate.json()["audit"]["status"] == "PROCESSING"
        return original_execute(db, order, video, file_storage, audit=audit)

    monkeypatch.setattr(workflow, "execute_video_audit", verify_durable_progress)
    reviewed = client.post(
        f"/api/v1/rework-tasks/{task_id}/review",
        json={
            "actorId": "quality-01",
            "videoId": persisted_video_id,
            "notes": "返工视频步骤完整",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["audit"]["decision"] == "PASS"
    assert reviewed.json()["task"]["status"] == "APPROVED"
    assert reviewed.json()["workOrder"]["status"] == "RELEASED"
    repeated = client.post(
        f"/api/v1/rework-tasks/{task_id}/review",
        json={"actorId": "quality-01", "videoId": persisted_video_id},
    )
    assert repeated.status_code == 200
    assert repeated.json()["audit"]["id"] == reviewed.json()["audit"]["id"]


@pytest.mark.parametrize("unexpected", [False, True])
def test_rework_failure_is_persisted_and_retryable(client, session, monkeypatch, unexpected):
    storage = MemoryStorage()
    app.dependency_overrides[get_file_storage] = lambda: storage
    order_id = seed_work_order(session, "WO-REWORK-FAIL")
    upload_and_inspect(client, order_id, "missing-step.mp4")
    case = client.get("/api/v1/exceptions").json()[0]
    client.post(f"/api/v1/exceptions/{case['id']}/confirm",
                json={"actorId": "tester", "reason": "test fixture"})
    assigned = client.post(f"/api/v1/exceptions/{case['id']}/rework-task", json={
        "actorId": "tester", "assigneeId": "tester", "instructions": "test recovery"})
    task_id = assigned.json()["reworkTask"]["id"]
    video = client.post(f"/api/v1/rework-tasks/{task_id}/videos",
                        files={"file": ("rework-normal.mp4", b"fixture", "video/mp4")}).json()
    from flowguard_api.routes import workflow
    original_execute = workflow.execute_video_audit

    def fail(*args, **kwargs):
        if unexpected:
            raise RuntimeError("private service detail")
        raise VideoInferenceError("Step 5 请求超时")

    monkeypatch.setattr(workflow, "execute_video_audit", fail)
    with TestClient(app, raise_server_exceptions=False) as errors_client:
        response = errors_client.post(f"/api/v1/rework-tasks/{task_id}/review", json={
            "actorId": "tester", "videoId": video["id"]})
    assert response.status_code == (500 if unexpected else 422)
    assert "private service detail" not in response.text
    with Session(session.bind) as observer:
        failed = observer.scalar(select(VideoAudit).where(VideoAudit.video_id == video["id"]))
        assert failed.status.value == "FAILED"
        assert observer.get(WorkOrder, order_id).status.value == "REWORK_SUBMITTED"
    detail = client.get(f"/api/v1/exceptions/{case['id']}").json()
    assert detail["status"] == "REWORK_SUBMITTED"
    monkeypatch.setattr(workflow, "execute_video_audit", original_execute)
    retry = client.post(f"/api/v1/rework-tasks/{task_id}/review", json={
        "actorId": "tester", "videoId": video["id"]})
    assert retry.status_code == 200
    assert retry.json()["audit"]["status"] == "COMPLETED"
    assert retry.json()["audit"]["id"] != failed.id


def test_occluded_video_requires_manual_review(client: TestClient, session: Session) -> None:
    storage = MemoryStorage()
    app.dependency_overrides[get_file_storage] = lambda: storage
    work_order_id = seed_work_order(session, "WO-WORKFLOW-002")

    audit = upload_and_inspect(client, work_order_id, "occluded.mp4")
    assert audit["decision"] == "INSUFFICIENT_EVIDENCE"
    exceptions = client.get("/api/v1/exceptions").json()
    exception = next(item for item in exceptions if item["workOrderId"] == work_order_id)
    assert exception["status"] == "MANUAL_REVIEW"
    detail = client.get(f"/api/v1/work-orders/{work_order_id}")
    assert detail.json()["status"] == "MANUAL_REVIEW"
