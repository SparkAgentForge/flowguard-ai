from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.models import Sop, SopStatus, SopStep, SopVersion


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
    client: TestClient, session: Session, monkeypatch
) -> None:
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
