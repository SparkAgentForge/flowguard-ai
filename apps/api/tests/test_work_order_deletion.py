from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowguard_api.infrastructure.storage import LocalFileStorage, get_file_storage
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

    audit = VideoAudit(
        work_order_id=order.id,
        video_id="video-placeholder",
        status=VideoAuditStatus.COMPLETED,
        decision=AuditDecision.VIOLATION,
        provider="stepfun",
        model_name="step-5",
        overall_pass=False,
        summary="发现异常",
        raw_response={"frame_asset_keys": ["frames/delete/frame-1.jpg"]},
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
    video = VideoAsset(
        id="video-delete-001",
        work_order_id=order.id,
        rework_task_id=task.id,
        filename="assembly.mp4",
        content_type="video/mp4",
        sha256="a" * 64,
        storage_key="videos/delete/assembly.mp4",
    )
    audit.video_id = video.id
    session.add_all(
        [
            video,
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
        "frame": "frames/delete/frame-1.jpg",
        "report": "reports/WO-DELETE-001/v1.pdf",
    }


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
