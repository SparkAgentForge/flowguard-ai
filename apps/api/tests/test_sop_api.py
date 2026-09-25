from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from flowguard_api.config import Settings
from flowguard_api.infrastructure.ai.manual_vision import Step5ManualVisionExtractor
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient
from flowguard_api.infrastructure.documents.pdf_renderer import PdfPageRenderer
from flowguard_api.infrastructure.storage import LocalFileStorage, get_file_storage
from flowguard_api.services.sop_extractor import (
    DocumentExtractionError,
    RuleBasedSopExtractor,
    get_sop_extractor,
)


def manual_docx() -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        for text in (
            "（1）在最下方插槽安装第一个风扇：先连接线缆，然后按压到位。",
            "（2）完成第一个风扇安装后，安装第二个风扇：先连接线缆，然后按压到位。",
            "（3）完成第二个风扇安装后，安装第三个风扇：先连接线缆，然后按压到位。",
            "（4）除上述三个规定安装动作之外的背景画面或其他活动。",
        )
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    with BytesIO() as output:
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", document)
        return output.getvalue()


def manual_pdf() -> bytes:
    with BytesIO() as output:
        document = canvas.Canvas(output)
        document.drawString(72, 760, "Install first fan")
        document.showPage()
        document.drawString(72, 760, "Install second fan")
        document.save()
        return output.getvalue()


class PageStorage:
    def __init__(self) -> None:
        self.assets: dict[str, bytes] = {}

    def put(self, key: str, content: bytes) -> None:
        self.assets[key] = content

    def get(self, key: str) -> bytes:
        return self.assets[key]

    def get_url(self, key: str, expires_seconds: int = 900) -> str:
        return f"https://rustfs.example/{key}?expires={expires_seconds}"


def upload_and_extract(client: TestClient) -> dict:
    uploaded = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "服务器风扇安装.docx",
                manual_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
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
    assert extracted["name"] == "服务器风扇安装"
    assert extracted["steps"][0]["name"] == "安装第一个风扇"
    assert extracted["steps"][1]["name"] == "安装第二个风扇"
    assert extracted["steps"][3]["required"] is False
    assert extracted["steps"][0]["code"] != "scan_part"
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


def test_document_extraction_rejects_unreadable_manual(client: TestClient, tmp_path: Path) -> None:
    client.app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(str(tmp_path))
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("broken.docx", b"not-a-docx", "application/octet-stream")},
    )
    assert uploaded.status_code == 201
    response = client.post(
        f"/api/v1/documents/{uploaded.json()['id']}/extract",
        json={"actorId": "engineer-01"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "DOCX 文档无法读取"


def test_pdf_pages_are_rendered_to_images() -> None:
    pages = PdfPageRenderer(dpi=72).render(manual_pdf())

    assert [page.page_number for page in pages] == [1, 2]
    assert all(page.content.startswith(b"\x89PNG\r\n\x1a\n") for page in pages)


def test_rule_based_extractor_does_not_read_pdf_text_layer() -> None:
    with pytest.raises(DocumentExtractionError, match="Step 5 视觉提取器"):
        RuleBasedSopExtractor().extract("manual.pdf", manual_pdf())


def test_step5_rejects_out_of_range_pdf_page_reference() -> None:
    extractor = Step5ManualVisionExtractor(PageStorage())
    with pytest.raises(DocumentExtractionError, match="有效的 PDF 页码"):
        extractor._parse(
            {
                "steps": [
                    {
                        "sequence": 1,
                        "name": "安装风扇",
                        "source_refs": [{"page": 3, "quote": "Install fan"}],
                    }
                ]
            },
            "manual.pdf",
            manual_pdf(),
            page_count=2,
        )


def test_pdf_visual_extraction_uploads_pages_and_sends_image_urls(client: TestClient) -> None:
    storage = PageStorage()
    step5 = Step5VisionClient(Settings(stepfun_api_key="test-key"))
    captured: dict = {}

    def post_json(url: str, payload: dict) -> dict:
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"name":"风扇安装","steps":['
                            '{"code":"step_01","sequence":1,"name":"安装第一个风扇",'
                            '"source_refs":[{"page":1,"quote":"Install first fan"}]},'
                            '{"code":"step_02","sequence":2,"name":"安装第二个风扇",'
                            '"source_refs":[{"page":2,"quote":"Install second fan"}]}]}'
                        )
                    }
                }
            ]
        }

    step5.post_json = post_json
    client.app.dependency_overrides[get_file_storage] = lambda: storage
    client.app.dependency_overrides[get_sop_extractor] = lambda: Step5ManualVisionExtractor(
        storage, client=step5
    )
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("fan-manual.pdf", manual_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201
    response = client.post(
        f"/api/v1/documents/{uploaded.json()['id']}/extract",
        json={"actorId": "engineer-01"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AI_EXTRACTED"
    assert [step["sourceRefs"][0]["page"] for step in response.json()["steps"]] == [1, 2]
    assert len(storage.assets) == 3  # Original PDF plus two rendered PNG pages.
    png_assets = [content for content in storage.assets.values() if content.startswith(b"\x89PNG")]
    assert len(png_assets) == 2
    parts = captured["payload"]["messages"][1]["content"]
    image_parts = [part for part in parts if part["type"] == "image_url"]
    assert len(image_parts) == 2
    assert all(
        part["image_url"]["url"].startswith("https://rustfs.example/")
        for part in image_parts
    )
    assert all("data:" not in part["image_url"]["url"] for part in image_parts)


def test_pdf_visual_extraction_without_step5_key_returns_422(client: TestClient) -> None:
    storage = PageStorage()
    client.app.dependency_overrides[get_file_storage] = lambda: storage
    client.app.dependency_overrides[get_sop_extractor] = lambda: Step5ManualVisionExtractor(
        storage, client=Step5VisionClient(Settings(stepfun_api_key=""))
    )
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("fan-manual.pdf", manual_pdf(), "application/pdf")},
    )
    response = client.post(
        f"/api/v1/documents/{uploaded.json()['id']}/extract",
        json={"actorId": "engineer-01"},
    )

    assert response.status_code == 422
    assert "FLOWGUARD_STEPFUN_API_KEY" in response.json()["detail"]
    assert len(storage.assets) == 1  # Only the original PDF was uploaded.
