from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.models import Sop, SopVersion


def seed_sop_version(session: Session) -> str:
    sop = Sop(code="PUMP-COVER", name="泵体端盖装配", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0")
    session.add_all([sop, version])
    session.commit()
    return version.id


def test_work_order_transition_api(client: TestClient, session: Session) -> None:
    version_id = seed_sop_version(session)
    created = client.post(
        "/api/v1/work-orders",
        json={
            "code": "WO-2026-001",
            "productCode": "PUMP-A01",
            "sopVersionId": version_id,
            "currentAssignee": "operator-01",
        },
    )

    assert created.status_code == 201
    work_order_id = created.json()["id"]

    transitioned = client.post(
        f"/api/v1/work-orders/{work_order_id}/transitions",
        json={
            "targetStatus": "INSPECTING",
            "actorId": "operator-01",
            "reason": "开始视频检测",
        },
    )

    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "INSPECTING"
    assert transitioned.json()["events"][0]["oldStatus"] == "CREATED"


def test_work_order_illegal_transition_returns_conflict(
    client: TestClient, session: Session
) -> None:
    version_id = seed_sop_version(session)
    created = client.post(
        "/api/v1/work-orders",
        json={"code": "WO-2026-002", "productCode": "PUMP-A01", "sopVersionId": version_id},
    )
    work_order_id = created.json()["id"]

    response = client.post(
        f"/api/v1/work-orders/{work_order_id}/transitions",
        json={"targetStatus": "ARCHIVED", "actorId": "quality-01"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "不允许从 CREATED 转换到 ARCHIVED"
