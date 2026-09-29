from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowguard_api.infrastructure.storage import LocalFileStorage, get_file_storage
from flowguard_api.infrastructure.storage.providers import S3FileStorage
from flowguard_api.models import (
    AuditDecision,
    AuditEvent,
    AuditFinding,
    ExceptionCase,
    ExceptionStatus,
    Notification,
    Report,
    ReworkTask,
    ReworkTaskStatus,
    Sop,
    SopStatus,
    SopStep,
    SopVersion,
    VideoAsset,
    VideoAudit,
    VideoAuditStatus,
    WorkOrder,
    WorkOrderStatus,
)
from flowguard_api.services.work_order_deletion import (
    WorkOrderStorageDeletionError,
    _owned_storage_keys,
    delete_work_order,
)


def seed_order_with_history(session: Session) -> tuple[str, str, dict[str, str]]:
    sop = Sop(code="SOP-DELETE", name="删除测试 SOP", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    step = SopStep(
        sop_version_id=version.id,
        code="install_part",
        sequence=1,
        name="安装零件",
        evidence_requirements=["出现安装动作"],
    )
    order = WorkOrder(
        code="WO-DELETE-001",
        product_code="PUMP-A01",
        sop_version_id=version.id,
        status=WorkOrderStatus.EXCEPTION_PENDING,
    )
    session.add_all([step, order])
    session.flush()

    video = VideoAsset(
        id="video-delete-001",
        work_order_id=order.id,
        filename="assembly.mp4",
        content_type="video/mp4",
        sha256="a" * 64,
        storage_key="videos/delete/assembly.mp4",
    )
    session.add(video)
    session.flush()
    audit = VideoAudit(
        work_order_id=order.id,
        video_id=video.id,
        status=VideoAuditStatus.COMPLETED,
        decision=AuditDecision.VIOLATION,
        provider="stepfun",
        model_name="step-5",
        overall_pass=False,
        summary="发现异常",
        raw_response={
            "frame_asset_keys": [
                "step5-frames/0123456789abcdef0123456789abcdef/frame-000001.jpg"
            ]
        },
    )
    session.add(audit)
    session.flush()
    exception = ExceptionCase(
        work_order_id=order.id,
        audit_id=audit.id,
        status=ExceptionStatus.PENDING,
        rule_code="STEP_MISSING",
        facts=["缺少步骤"],
    )
    session.add(exception)
    session.flush()
    task = ReworkTask(
        exception_id=exception.id,
        work_order_id=order.id,
        assignee_id="operator-01",
        instructions="重新安装",
        status=ReworkTaskStatus.ASSIGNED,
        created_by="quality-01",
    )
    session.add(task)
    session.flush()
    video.rework_task_id = task.id
    rework_video = VideoAsset(
        id="video-delete-002",
        work_order_id=order.id,
        rework_task_id=task.id,
        filename="rework.mp4",
        content_type="video/mp4",
        sha256="c" * 64,
        storage_key=f"rework/{task.id}/rework.mp4",
    )
    audit.video_id = video.id
    session.add_all(
        [
            video,
            rework_video,
            AuditFinding(
                audit_id=audit.id,
                sop_step_id=step.id,
                sequence=1,
                step_name=step.name,
                detected=False,
                confidence=20,
                evidence_status="MISSING",
                evidence_score=20,
                evidence="未发现",
            ),
            Notification(
                work_order_id=order.id,
                rework_task_id=task.id,
                recipient_id="operator-01",
                event_type="REWORK_ASSIGNED",
                title="需要返工",
                message="重新安装",
            ),
            Report(
                work_order_id=order.id,
                version=1,
                content={"outcome": "VIOLATION"},
                pdf_storage_key="reports/WO-DELETE-001/v1.pdf",
                pdf_sha256="b" * 64,
            ),
            AuditEvent(
                work_order_id=order.id,
                event_type="CREATED",
                actor_id="quality-01",
                old_status=WorkOrderStatus.CREATED,
                new_status=WorkOrderStatus.EXCEPTION_PENDING,
            ),
        ]
    )
    session.commit()
    return order.id, task.id, {
        "video": video.storage_key,
        "rework_video": rework_video.storage_key,
        "preview": f"video-previews/{video.id}.mp4",
        "rework_preview": f"video-previews/{rework_video.id}.mp4",
        "frame": "step5-frames/0123456789abcdef0123456789abcdef/frame-000001.jpg",
        "report": "reports/WO-DELETE-001/v1.pdf",
        "orphan_video": f"videos/{order.id}/orphan.mp4",
        "orphan_frame": f"step5-frames/{order.id}/failed-run/frame-000002.jpg",
        "orphan_report": f"reports/{order.id}/orphan.pdf",
        "orphan_rework": f"rework/{task.id}/orphan.mp4",
    }


def test_owned_storage_keys_include_previews_without_shared_assets() -> None:
    keys = _owned_storage_keys(
        [SimpleNamespace(id="video-1", storage_key="videos/order-1/assembly.mp4")],
        [SimpleNamespace(pdf_storage_key="reports/order-1/v1.pdf")],
        [
            SimpleNamespace(
                provider="stepfun",
                raw_response={
                    "frame_asset_keys": [
                        "step5-frames/run-1/frame.jpg",
                        "documents/shared-manual.pdf",
                    ]
                },
            ),
            SimpleNamespace(
                provider="deepstream",
                raw_response={"frame_asset_keys": ["step5-frames/other/frame.jpg"]},
            ),
        ],
    )

    assert keys == {
        "videos/order-1/assembly.mp4",
        "video-previews/video-1.mp4",
        "reports/order-1/v1.pdf",
        "step5-frames/run-1/frame.jpg",
    }


def test_local_storage_lists_only_work_order_prefix(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path))
    owned = "step5-frames/order-1/run/frame.jpg"
    storage.put(owned, b"frame")
    storage.put("step5-frames/order-10/run/frame.jpg", b"other")

    assert storage.list_prefix("step5-frames/order-1/") == [owned]


def test_rustfs_storage_lists_all_pages_for_prefix() -> None:
    storage = object.__new__(S3FileStorage)
    storage._bucket_ready = True
    storage.bucket = "flowguard"
    storage._client = Mock()
    storage._client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "videos/order-1/first.mp4"}]},
        {"Contents": [{"Key": "videos/order-1/second.mp4"}]},
    ]

    assert storage.list_prefix("videos/order-1/") == [
        "videos/order-1/first.mp4",
        "videos/order-1/second.mp4",
    ]
    storage._client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="flowguard", Prefix="videos/order-1/"
    )


@pytest.mark.parametrize("failure_stage", ["list", "delete"])
def test_storage_failure_does_not_commit_work_order_deletion(failure_stage: str) -> None:
    order = SimpleNamespace(id="order-1", code="WO-1", status=WorkOrderStatus.CREATED)
    video = SimpleNamespace(id="video-1", storage_key="videos/order-1/video.mp4")
    session = Mock()
    session.get.return_value = order
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: []),
        SimpleNamespace(all=lambda: []),
        SimpleNamespace(all=lambda: [video]),
        SimpleNamespace(all=lambda: []),
    ]
    storage = Mock()
    storage.list_prefix.return_value = []
    if failure_stage == "list":
        storage.list_prefix.side_effect = OSError("RustFS unavailable")
    else:
        storage.delete.side_effect = OSError("RustFS unavailable")

    with pytest.raises(WorkOrderStorageDeletionError, match="请重试"):
        delete_work_order(session, storage, order.id, "quality-01", order.code)

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    session.delete.assert_not_called()


def test_delete_work_order_removes_associations_and_storage(
    client: TestClient, session: Session, tmp_path
) -> None:
    storage = LocalFileStorage(str(tmp_path))
    client.app.dependency_overrides[get_file_storage] = lambda: storage
    work_order_id, task_id, keys = seed_order_with_history(session)
    for key in keys.values():
        storage.put(key, b"test")

    response = client.request(
        "DELETE",
        f"/api/v1/work-orders/{work_order_id}",
        json={"actorId": "quality-01", "confirmation": "WO-DELETE-001"},
    )

    assert response.status_code == 204
    assert session.get(WorkOrder, work_order_id) is None
    assert (
        session.scalars(select(VideoAsset).where(VideoAsset.work_order_id == work_order_id)).all()
        == []
    )
    assert (
        session.scalars(select(VideoAudit).where(VideoAudit.work_order_id == work_order_id)).all()
        == []
    )
    assert (
        session.scalars(
            select(ExceptionCase).where(ExceptionCase.work_order_id == work_order_id)
        ).all()
        == []
    )
    assert session.get(ReworkTask, task_id) is None
    assert session.scalars(select(Report).where(Report.work_order_id == work_order_id)).all() == []
    assert all(not storage.exists(key) for key in keys.values())
    assert session.scalar(select(Sop).where(Sop.code == "SOP-DELETE")) is not None


def test_delete_work_order_storage_failure_preserves_record_for_retry(
    client: TestClient, session: Session, tmp_path
) -> None:
    class FlakyStorage(LocalFileStorage):
        fail_key: str | None = None

        def delete(self, key: str) -> None:
            if key == self.fail_key:
                raise OSError("RustFS unavailable")
            super().delete(key)

    storage = FlakyStorage(str(tmp_path))
    client.app.dependency_overrides[get_file_storage] = lambda: storage
    work_order_id, _, keys = seed_order_with_history(session)
    for key in keys.values():
        storage.put(key, b"test")
    storage.fail_key = keys["report"]

    request = {"actorId": "quality-01", "confirmation": "WO-DELETE-001"}
    first = client.request("DELETE", f"/api/v1/work-orders/{work_order_id}", json=request)

    assert first.status_code == 503
    assert "重试" in first.json()["detail"]
    assert first.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "RustFS unavailable" not in first.text
    assert session.get(WorkOrder, work_order_id) is not None

    storage.fail_key = None
    second = client.request("DELETE", f"/api/v1/work-orders/{work_order_id}", json=request)

    assert second.status_code == 204
    assert session.get(WorkOrder, work_order_id) is None
    assert all(not storage.exists(key) for key in keys.values())


def test_delete_work_order_requires_exact_confirmation(
    client: TestClient, session: Session
) -> None:
    sop = Sop(code="SOP-CONFIRM", name="确认测试", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    order = WorkOrder(code="WO-CONFIRM-001", product_code="PUMP-A01", sop_version_id=version.id)
    session.add(order)
    session.commit()

    response = client.request(
        "DELETE",
        f"/api/v1/work-orders/{order.id}",
        json={"actorId": "quality-01", "confirmation": "wrong"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "请输入完全一致的工单编号进行确认"
    assert session.get(WorkOrder, order.id) is not None


def test_delete_work_order_protects_archived_records(client: TestClient, session: Session) -> None:
    sop = Sop(code="SOP-ARCHIVE", name="归档测试", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    order = WorkOrder(
        code="WO-ARCHIVE-001",
        product_code="PUMP-A01",
        sop_version_id=version.id,
        status=WorkOrderStatus.ARCHIVED,
    )
    session.add(order)
    session.commit()

    response = client.request(
        "DELETE",
        f"/api/v1/work-orders/{order.id}",
        json={"actorId": "quality-01", "confirmation": "WO-ARCHIVE-001"},
    )

    assert response.status_code == 409
    assert "不能删除" in response.json()["detail"]
    assert session.get(WorkOrder, order.id) is not None
