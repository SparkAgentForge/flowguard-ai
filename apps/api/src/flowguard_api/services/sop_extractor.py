from dataclasses import dataclass, field
from typing import Protocol


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


class SopExtractor(Protocol):
    def extract(self, filename: str, content: bytes) -> ExtractedSop: ...


class MockSopExtractor:
    def extract(self, filename: str, content: bytes) -> ExtractedSop:
        if not content:
            raise ValueError("文档内容为空")
        return ExtractedSop(
            code="PUMP-COVER-ASSEMBLY",
            name="泵体端盖装配",
            product_code="PUMP-A01",
            version="1.0-draft",
            steps=[
                ExtractedStep(
                    code="scan_part",
                    sequence=1,
                    name="扫描泵体二维码",
                    evidence_requirements=["画面中出现扫码动作"],
                    source_refs=[ExtractedSourceRef(1, None, "扫描泵体二维码")],
                ),
                ExtractedStep(
                    code="install_seal",
                    sequence=2,
                    name="安装绿色密封圈",
                    preconditions=["scan_part"],
                    evidence_requirements=["密封圈完全进入槽位"],
                    source_refs=[ExtractedSourceRef(1, None, "安装绿色密封圈")],
                ),
                ExtractedStep(
                    code="install_cover",
                    sequence=3,
                    name="安装端盖并锁紧",
                    preconditions=["install_seal"],
                    evidence_requirements=["端盖就位并使用扭矩扳手"],
                    source_refs=[ExtractedSourceRef(1, None, "安装端盖并锁紧")],
                ),
                ExtractedStep(
                    code="apply_label",
                    sequence=4,
                    name="粘贴质检标签",
                    preconditions=["install_cover"],
                    evidence_requirements=["成品表面出现质检标签"],
                    source_refs=[ExtractedSourceRef(1, None, "粘贴质检标签")],
                ),
            ],
        )


def get_sop_extractor() -> SopExtractor:
    return MockSopExtractor()
