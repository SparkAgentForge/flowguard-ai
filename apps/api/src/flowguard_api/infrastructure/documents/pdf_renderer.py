"""Render PDF pages into image bytes for multimodal inference."""

from dataclasses import dataclass
from io import BytesIO

from flowguard_api.services.sop_extractor import DocumentExtractionError


@dataclass(frozen=True)
class RenderedPdfPage:
    """A rendered page with its one-based page number."""

    page_number: int
    content: bytes
    media_type: str = "image/png"


class PdfPageRenderer:
    """Convert every PDF page to a bounded-resolution PNG image.

    PDFium is imported lazily so DOCX/rule-based local workflows do not need
    to import the PDF engine until the visual PDF path is actually selected.
    """

    def __init__(self, dpi: int = 144, max_pages: int = 50) -> None:
        if dpi <= 0:
            raise ValueError("PDF 渲染 DPI 必须大于 0")
        if max_pages <= 0:
            raise ValueError("PDF 最大页数必须大于 0")
        self.dpi = dpi
        self.max_pages = max_pages

    def render(self, content: bytes) -> list[RenderedPdfPage]:
        if not content:
            raise DocumentExtractionError("PDF 文档内容为空")
        try:
            import pypdfium2 as pdfium
        except ImportError as error:
            raise DocumentExtractionError("PDF 视觉解析需要安装 pypdfium2") from error

        try:
            document = pdfium.PdfDocument(content)
        except Exception as error:  # PDFium raises implementation-specific parser errors.
            raise DocumentExtractionError("PDF 文档无法渲染") from error

        try:
            if len(document) == 0:
                raise DocumentExtractionError("PDF 文档没有页面")
            if len(document) > self.max_pages:
                raise DocumentExtractionError(
                    f"PDF 页面数超过 {self.max_pages} 页视觉解析限制"
                )
            pages: list[RenderedPdfPage] = []
            for index in range(len(document)):
                page = document[index]
                try:
                    bitmap = page.render(scale=self.dpi / 72)
                    try:
                        image = bitmap.to_pil()
                        try:
                            with BytesIO() as output:
                                image.save(output, format="PNG")
                                page_image = output.getvalue()
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                pages.append(
                    RenderedPdfPage(
                        page_number=index + 1,
                        content=page_image,
                    )
                )
            return pages
        except DocumentExtractionError:
            raise
        except Exception as error:  # Rendering failures are backend-specific.
            raise DocumentExtractionError("PDF 页面渲染失败") from error
        finally:
            document.close()
