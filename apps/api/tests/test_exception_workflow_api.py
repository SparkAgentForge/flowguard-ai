from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.application import app
from flowguard_api.infrastructure.storage.factory import get_file_storage
from flowguard_api.models import Sop, SopStatus, SopStep, SopVersion, WorkOrder


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


def test_exception_rework_and_release_flow(client: TestClient, session: Session) -> None:
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
    assert refreshed_exception["reworkTask"]["status"] == "SUBMITTED"
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
