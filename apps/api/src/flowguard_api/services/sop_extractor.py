"""Extract candidate SOPs from uploaded operation manuals.

The extractor intentionally returns an editable ``AI_EXTRACTED`` draft. It
does not publish a SOP or make a video decision. DOCX uses deterministic
document parsing; PDF is rendered as images by the Step 5 adapter.
"""

import re
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated, Protocol
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from fastapi import Depends

from flowguard_api.config import get_settings
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.storage.factory import get_file_storage


class DocumentExtractionError(ValueError):
    """Raised when an uploaded manual cannot be read or contains no steps."""


@dataclass(frozen=True)
class ExtractedSourceRef:
    page: int | None
    paragraph: str | None
    quote: str


@dataclass(frozen=True)
class ExtractedStep:
    code: str
    sequence: int
    name: str
    required: bool = True
    preconditions: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    on_missing: str = "BLOCK"
    source_refs: list[ExtractedSourceRef] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedSop:
    code: str
    name: str
    product_code: str
    version: str
    steps: list[ExtractedStep]


@dataclass(frozen=True)
class SourceBlock:
    text: str
    page: int | None
    paragraph: str | None
    sequence: int | None = None


class SopExtractor(Protocol):
    def extract(self, filename: str, content: bytes) -> ExtractedSop: ...


class OperationManualReader(Protocol):
    def read(self, filename: str, content: bytes) -> list[SourceBlock]: ...


class DocumentOperationManualReader:
    """Read DOCX paragraphs for the local deterministic extractor."""

    _WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    def read(self, filename: str, content: bytes) -> list[SourceBlock]:
        suffix = Path(filename).suffix.lower()
        if suffix == ".docx":
            return self._read_docx(content)
        if suffix == ".pdf":
            raise DocumentExtractionError("PDF 请启用 Step 5 视觉提取器")
        raise DocumentExtractionError("仅支持 PDF 和 DOCX 操作手册")

    def _read_docx(self, content: bytes) -> list[SourceBlock]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                document_xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError, OSError) as error:
            raise DocumentExtractionError("DOCX 文档无法读取") from error

        try:
            root = ElementTree.fromstring(document_xml)
        except ElementTree.ParseError as error:
            raise DocumentExtractionError("DOCX 文档结构无效") from error

        blocks: list[SourceBlock] = []
        for index, paragraph in enumerate(root.findall(".//w:body/w:p", self._WORD_NAMESPACE), 1):
            text = "".join(
                node.text or ""
                for node in paragraph.findall(".//w:t", self._WORD_NAMESPACE)
            )
            text = _normalize_text(text)
            if text:
                blocks.append(SourceBlock(text=text, page=1, paragraph=str(index)))
        if not blocks:
            raise DocumentExtractionError("DOCX 文档没有可读取的正文")
        return blocks

class RuleBasedSopExtractor:
    """Build an editable SOP from numbered manual instructions."""

    _NUMBERED = re.compile(r"^\s*[（(【\[]?\s*(\d{1,3})\s*[）)】\]]\s*(.*)$")
    _NUMBERED_PUNCTUATED = re.compile(r"^\s*(\d{1,3})\s*[、.．:：]\s*(.*)$")
    _ACTION = re.compile(
        r"(?:安装|拆卸|卸下|放置|连接|按压|滑入|推入|固定|锁紧|粘贴|扫描|清洁|检查|"
        r"对齐|插入|拔出|移除|打开|关闭|更换|取出|调整|移动|按下|切换|涂抹|拧紧|旋紧)"
        r"[^，。：:；;。]*"
    )
    _NOISE_MARKERS = ("除上述", "背景画面", "其他活动", "空闲时段", "无关的移动")

    def __init__(self, reader: OperationManualReader | None = None) -> None:
        self.reader = reader or DocumentOperationManualReader()

    def extract(self, filename: str, content: bytes) -> ExtractedSop:
        if not content:
            raise DocumentExtractionError("文档内容为空")
        blocks = self.reader.read(filename, content)
        numbered = self._numbered_blocks(blocks)
        if not numbered:
            raise DocumentExtractionError("未能从操作手册中识别出有序操作步骤")
        steps = self._build_steps(numbered)
        digest = sha256(content).hexdigest()[:12].upper()
        document_name = Path(filename).stem.strip() or "操作手册"
        return ExtractedSop(
            code=f"SOP-DOC-{digest}",
            name=document_name[:255],
            product_code="UNSPECIFIED",
            version="1.0-draft",
            steps=steps,
        )

    def _numbered_blocks(self, blocks: list[SourceBlock]) -> list[SourceBlock]:
        result: list[SourceBlock] = []
        current: SourceBlock | None = None
        current_number: int | None = None
        for block in blocks:
            match = self._NUMBERED.match(block.text) or self._NUMBERED_PUNCTUATED.match(
                block.text
            )
            if match:
                if current is not None and current_number is not None:
                    result.append(current)
                current_number = int(match.group(1))
                current = SourceBlock(
                    text=f"{current_number}. {match.group(2).strip()}",
                    page=block.page,
                    paragraph=block.paragraph,
                    sequence=current_number,
                )
            elif current is not None:
                current = SourceBlock(
                    text=_normalize_text(f"{current.text} {block.text}"),
                    page=current.page,
                    paragraph=current.paragraph,
                    sequence=current.sequence,
                )
        if current is not None and current_number is not None:
            result.append(current)
        return result

    def _build_steps(self, blocks: list[SourceBlock]) -> list[ExtractedStep]:
        steps: list[ExtractedStep] = []
        for position, block in enumerate(blocks, 1):
            sequence = block.sequence or position
            instruction = re.sub(r"^\s*\d{1,3}[.]\s*", "", block.text).strip()
            noise = any(marker in instruction for marker in self._NOISE_MARKERS)
            name = self._step_name(instruction, noise, sequence)
            code = f"step_{sequence:02d}"
            preconditions = [step.code for step in steps if step.required]
            steps.append(
                ExtractedStep(
                    code=code,
                    sequence=sequence,
                    name=name[:255],
                    required=not noise,
                    preconditions=preconditions,
                    evidence_requirements=[instruction[:500]],
                    on_missing="IGNORE" if noise else "BLOCK",
                    source_refs=[
                        ExtractedSourceRef(
                            page=block.page,
                            paragraph=block.paragraph,
                            quote=instruction[:500],
                        )
                    ],
                )
            )
        return steps

    def _step_name(self, instruction: str, noise: bool, sequence: int) -> str:
        if noise:
            return "背景或其他非规定活动"
        before_details = re.split(r"[：:]", instruction, maxsplit=1)[0]
        actions = list(self._ACTION.finditer(before_details))
        if actions:
            return actions[-1].group(0).strip(" ，,。；;")
        first_clause = re.split(r"[，,。；;]", before_details, maxsplit=1)[-1]
        return first_clause.strip() or f"第 {sequence} 步"


def get_sop_extractor(
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> SopExtractor:
    """Return the configured document extractor.

    ``mock`` remains accepted as a local DOCX parser alias; PDF is visual-only.
    """

    provider = get_settings().sop_extractor_provider.lower()
    if provider == "stepfun":
        from flowguard_api.infrastructure.ai.manual_vision import Step5ManualVisionExtractor

        return Step5ManualVisionExtractor(storage)
    if provider in {"rule_based", "document", "mock"}:
        return RuleBasedSopExtractor()
    raise RuntimeError(f"不支持的 SOP 提取器: {provider}")


def extract_document_text(filename: str, content: bytes) -> list[SourceBlock]:
    """Expose document reading for diagnostics and focused unit tests."""

    return DocumentOperationManualReader().read(filename, content)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
