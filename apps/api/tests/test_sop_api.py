from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from flowguard_api.storage import LocalFileStorage, get_file_storage


def upload_and_extract(client: TestClient) -> dict:
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("泵体端盖装配.pdf", b"mock pdf content", "application/pdf")},
    )
    assert uploaded.status_code == 201
    extracted = client.post(
        f"/api/v1/documents/{uploaded.json()['id']}/extract",
        json={"actorId": "engineer-01"},
    )
    assert extracted.status_code == 200
    return extracted.json()


def test_document_upload_rejects_unsupported_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"not supported", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "仅支持 PDF 和 DOCX 文档"


def test_sop_review_and_publish_flow(client: TestClient, session: Session, tmp_path: Path) -> None:
    client.app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(str(tmp_path))
    extracted = upload_and_extract(client)

    assert extracted["status"] == "AI_EXTRACTED"
    assert len(extracted["steps"]) == 4
    assert extracted["steps"][1]["sourceRefs"][0]["fileId"]

    version_id = extracted["id"]
    invalid_publish = client.post(
        f"/api/v1/sop-versions/{version_id}/publish",
        json={"actorId": "engineer-01"},
    )
    assert invalid_publish.status_code == 409

    for action, actor, expected in (
        ("submit-review", "engineer-01", "IN_REVIEW"),
        ("approve", "reviewer-01", "APPROVED"),
        ("publish", "reviewer-01", "PUBLISHED"),
    ):
        response = client.post(
            f"/api/v1/sop-versions/{version_id}/{action}",
            json={"actorId": actor},
        )
        assert response.status_code == 200
        assert response.json()["status"] == expected

    detail = client.get(f"/api/v1/sop-versions/{version_id}")
    assert detail.status_code == 200
    assert detail.json()["publishedAt"] is not None
    assert [event["newStatus"] for event in detail.json()["events"]] == [
        "AI_EXTRACTED",
        "IN_REVIEW",
        "APPROVED",
        "PUBLISHED",
    ]
