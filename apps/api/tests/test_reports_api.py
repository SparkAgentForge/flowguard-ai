from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.main import app
from flowguard_api.models import Sop, SopStatus, SopStep, SopVersion, WorkOrder
from flowguard_api.storage import get_file_storage


class MemoryStorage:
    def __init__(self) -> None:
        self.content: dict[str, bytes] = {}

    def put(self, key: str, content: bytes) -> None:
        self.content[key] = content

    def get(self, key: str) -> bytes:
        return self.content[key]


def seed_work_order(session: Session) -> str:
    sop = Sop(code="REPORT-SOP", name="报告测试 SOP", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0", status=SopStatus.PUBLISHED)
    session.add(version)
    session.flush()
    session.add_all(
        [
            SopStep(sop_version_id=version.id, code="scan", sequence=1, name="扫描零件"),
            SopStep(sop_version_id=version.id, code="seal", sequence=2, name="安装密封圈"),
        ]
    )
    work_order = WorkOrder(code="WO-REPORT-001", product_code="PUMP-A01", sop_version_id=version.id)
    session.add(work_order)
    session.commit()
    return work_order.id


def test_completed_work_order_generates_immutable_json_and_pdf(
    client: TestClient, session: Session
) -> None:
    storage = MemoryStorage()
    app.dependency_overrides[get_file_storage] = lambda: storage
    work_order_id = seed_work_order(session)
    uploaded = client.post(
        f"/api/v1/work-orders/{work_order_id}/videos",
        files={"file": ("normal.mp4", BytesIO(b"normal-video"), "video/mp4")},
    )
    inspected = client.post(
        f"/api/v1/work-orders/{work_order_id}/inspect",
        json={"videoId": uploaded.json()["id"], "actorId": "operator-01"},
    )
    assert inspected.json()["decision"] == "PASS"

    report = client.get(f"/api/v1/reports/{work_order_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["content"]["outcome"] == "VERIFIED"
    assert body["content"]["audits"][0]["model"] == "deterministic-demo"
    assert body["content"]["videos"][0]["sha256"]

    repeated = client.get(f"/api/v1/reports/{work_order_id}")
    assert repeated.json()["id"] == body["id"]
    pdf = client.get(f"/api/v1/reports/{work_order_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["etag"] == body["pdfSha256"]

    listed = client.get("/api/v1/reports")
    assert listed.status_code == 200
    assert listed.json()[0]["workOrderCode"] == "WO-REPORT-001"
