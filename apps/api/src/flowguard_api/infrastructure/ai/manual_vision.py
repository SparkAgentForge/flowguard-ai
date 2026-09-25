"""Step 5 visual extraction for PDF operation manuals."""

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from flowguard_api.config import get_settings
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.stepfun_client import Step5VisionClient
from flowguard_api.infrastructure.documents.pdf_renderer import PdfPageRenderer
from flowguard_api.services.sop_extractor import (
    DocumentExtractionError,
    ExtractedSop,
    ExtractedSourceRef,
    ExtractedStep,
    RuleBasedSopExtractor,
)


class Step5ManualVisionExtractor:
    """Turn PDF page images into an editable AI_EXTRACTED SOP draft."""

    _CODE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")

    def __init__(
        self,
        storage: FileStorage | None,
        renderer: PdfPageRenderer | None = None,
        client: Step5VisionClient | None = None,
    ) -> None:
        settings = get_settings()
        self.storage = storage
        self.renderer = renderer or PdfPageRenderer(
            dpi=settings.sop_manual_page_dpi,
            max_pages=settings.sop_manual_max_pages,
        )
        self.client = client or Step5VisionClient(settings)
        self.docx_fallback = RuleBasedSopExtractor()

    def extract(self, filename: str, content: bytes) -> ExtractedSop:
        if Path(filename).suffix.lower() != ".pdf":
            return self.docx_fallback.extract(filename, content)
        if not content:
            raise DocumentExtractionError("文档内容为空")
        if self.storage is None or not hasattr(self.storage, "get_url"):
            raise DocumentExtractionError("Step 5 PDF 视觉解析需要配置 RustFS URL")
        if not self.client.settings.stepfun_api_key:
            raise DocumentExtractionError("未配置 FLOWGUARD_STEPFUN_API_KEY")
        try:
            pages = self.renderer.render(content)
            page_parts: list[dict] = [
                {
                    "type": "text",
                    "text": self._prompt(filename, len(pages)),
                }
            ]
            digest = sha256(content).hexdigest()[:16]
            for page in pages:
                key = f"sop-manual-pages/{digest}/page-{page.page_number:04d}.png"
                self.storage.put(key, page.content)
                url = self.storage.get_url(
                    key, get_settings().stepfun_frame_url_expires_seconds
                )
                page_parts.extend(
                    [
                        {"type": "text", "text": f"下面是操作手册第 {page.page_number} 页"},
                        {"type": "image_url", "image_url": {"url": url}},
                    ]
                )
            raw_response = self.client.chat(
                content=page_parts,
                system_prompt=(
                    "你是工业操作手册解析器。只根据提供的 PDF 页面图像提取 SOP，"
                    "禁止补全看不见的步骤；必须保留页面编号和可核验的原文引用。"
                ),
            )
            payload = self.client.response_payload(raw_response)
            return self._parse(payload, filename, content, len(pages))
        except DocumentExtractionError:
            raise
        except Exception as error:
            raise DocumentExtractionError(f"Step 5 PDF 视觉解析失败: {error}") from error

    @staticmethod
    def _prompt(filename: str, page_count: int) -> str:
        return (
            f"这是操作手册《{Path(filename).name}》，共 {page_count} 页。请逐页阅读图像，"
            "抽取规定的、有顺序的操作步骤，不要依赖 PDF 文本层。背景、示例、注意事项和"
            "无法确认的活动不要伪造成必需步骤。只输出 JSON，不要 Markdown。格式必须是："
            '{"code":"SOP-...","name":"...","product_code":"...",'
            '"version":"1.0-draft","steps":[{"code":"step_01",'
            '"sequence":1,"name":"...","required":true,"preconditions":[],'
            '"evidence_requirements":["..."],"on_missing":"BLOCK",'
            '"source_refs":[{"page":1,"quote":"页面中能核验步骤的原文"}]}]}'
        )

    def _parse(
        self,
        payload: dict[str, Any],
        filename: str,
        content: bytes,
        page_count: int,
    ) -> ExtractedSop:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise DocumentExtractionError("Step 5 未从 PDF 页面中识别出 SOP 步骤")
        steps: list[ExtractedStep] = []
        seen_sequences: set[int] = set()
        seen_codes: set[str] = set()
        for position, raw_step in enumerate(raw_steps, 1):
            if not isinstance(raw_step, dict):
                raise DocumentExtractionError("Step 5 返回了无效的 SOP 步骤")
            sequence = _as_positive_int(raw_step.get("sequence"), position)
            if sequence in seen_sequences:
                raise DocumentExtractionError(f"Step 5 返回了重复的步骤序号: {sequence}")
            seen_sequences.add(sequence)
            required = bool(raw_step.get("required", True))
            code = _safe_code(raw_step.get("code"), sequence)
            if code in seen_codes:
                raise DocumentExtractionError(f"Step 5 返回了重复的步骤编码: {code}")
            seen_codes.add(code)
            name = str(raw_step.get("name") or f"第 {sequence} 步").strip()[:255]
            preconditions = _string_list(raw_step.get("preconditions"))
            evidence = _string_list(raw_step.get("evidence_requirements"))
            if not evidence:
                evidence = [name]
            source_refs = _source_refs(raw_step.get("source_refs"))
            if not source_refs or any(
                ref.page is None or ref.page > page_count for ref in source_refs
            ):
                raise DocumentExtractionError(f"步骤 {sequence} 缺少有效的 PDF 页码与原文引用")
            steps.append(
                ExtractedStep(
                    code=code,
                    sequence=sequence,
                    name=name,
                    required=required,
                    preconditions=preconditions,
                    evidence_requirements=evidence,
                    on_missing=("BLOCK" if required else "IGNORE"),
                    source_refs=source_refs,
                )
            )
        digest = sha256(content).hexdigest()[:12].upper()
        return ExtractedSop(
            code=f"SOP-DOC-{digest}",
            name=str(payload.get("name") or Path(filename).stem or "操作手册")[:255],
            product_code=str(payload.get("product_code") or "UNSPECIFIED")[:100],
            version="1.0-draft",
            steps=steps,
        )


def _safe_code(value: object, sequence: int) -> str:
    code = str(value or f"step_{sequence:02d}").strip()
    return code if Step5ManualVisionExtractor._CODE.fullmatch(code) else f"step_{sequence:02d}"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:500] for item in value if str(item).strip()]


def _source_refs(value: object) -> list[ExtractedSourceRef]:
    if not isinstance(value, list):
        return []
    refs: list[ExtractedSourceRef] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()[:500]
        if not quote:
            continue
        refs.append(
            ExtractedSourceRef(
                page=_as_optional_int(item.get("page")),
                paragraph=None,
                quote=quote,
            )
        )
    return refs


def _as_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_optional_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
