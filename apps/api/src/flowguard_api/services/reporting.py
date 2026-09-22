import hashlib
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowguard_api.models import (
    Document,
    ExceptionCase,
    Report,
    ReworkTask,
    Sop,
    SopVersion,
    VideoAsset,
    VideoAudit,
    WorkOrder,
    WorkOrderStatus,
)
from flowguard_api.storage import FileStorage


class ReportNotReady(ValueError):
    pass


def build_report_content(session: Session, work_order: WorkOrder) -> dict:
    if work_order.status not in {
        WorkOrderStatus.VERIFIED,
        WorkOrderStatus.RELEASED,
        WorkOrderStatus.ARCHIVED,
    }:
        raise ReportNotReady("工作单尚未完成检测或返工复核，不能归档")
    version = session.get(SopVersion, work_order.sop_version_id)
    sop = session.get(Sop, version.sop_id) if version else None
    document = (
        session.get(Document, version.source_document_id)
        if version and version.source_document_id
        else None
    )
    audits = session.scalars(
        select(VideoAudit)
        .options(selectinload(VideoAudit.findings))
        .where(VideoAudit.work_order_id == work_order.id)
        .order_by(VideoAudit.created_at)
    ).all()
    exception = session.scalar(
        select(ExceptionCase).where(ExceptionCase.work_order_id == work_order.id)
    )
    rework = session.scalar(select(ReworkTask).where(ReworkTask.work_order_id == work_order.id))
    videos = session.scalars(
        select(VideoAsset)
        .where(VideoAsset.work_order_id == work_order.id)
        .order_by(VideoAsset.created_at)
    ).all()
    return {
        "schemaVersion": "1.0",
        "workOrder": {
            "id": work_order.id,
            "code": work_order.code,
            "productCode": work_order.product_code,
            "status": work_order.status.value,
        },
        "sop": {
            "id": version.id if version else None,
            "code": sop.code if sop else None,
            "name": sop.name if sop else None,
            "version": version.version if version else None,
            "sourceDocumentSha256": document.sha256 if document else None,
        },
        "videos": [
            {
                "id": video.id,
                "filename": video.filename,
                "sha256": video.sha256,
                "kind": "REWORK" if video.rework_task_id else "ORIGINAL",
            }
            for video in videos
        ],
        "audits": [
            {
                "id": audit.id,
                "decision": audit.decision.value,
                "provider": audit.provider,
                "model": audit.model_name,
                "promptVersion": "video-audit-v1",
                "summary": audit.summary,
                "findings": [
                    {
                        "sequence": finding.sequence,
                        "stepName": finding.step_name,
                        "detected": finding.detected,
                        "confidence": finding.confidence,
                        "startSeconds": finding.start_seconds,
                        "endSeconds": finding.end_seconds,
                        "evidence": finding.evidence,
                        "frameTimestamps": finding.frame_timestamps,
                    }
                    for finding in sorted(audit.findings, key=lambda item: item.sequence)
                ],
            }
            for audit in audits
        ],
        "humanDecision": (
            {
                "status": exception.status.value,
                "reason": exception.human_reason,
                "reviewedBy": exception.reviewed_by,
                "reviewedAt": exception.reviewed_at.isoformat() if exception.reviewed_at else None,
            }
            if exception
            else None
        ),
        "rework": (
            {
                "taskId": rework.id,
                "assigneeId": rework.assignee_id,
                "instructions": rework.instructions,
                "status": rework.status.value,
                "reviewedBy": rework.reviewed_by,
                "reviewNotes": rework.review_notes,
            }
            if rework
            else None
        ),
        "outcome": "RELEASED_AFTER_REWORK"
        if work_order.status == WorkOrderStatus.RELEASED
        else "VERIFIED",
    }


def render_report_pdf(content: dict) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyCN", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9, leading=14
    )
    heading = ParagraphStyle(
        "HeadingCN",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=14,
        leading=20,
        spaceBefore=10,
    )
    title = ParagraphStyle(
        "TitleCN",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
    )
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=f"FlowGuard {content['workOrder']['code']} 审计报告",
    )
    story = [Paragraph("FlowGuard AI 装配审计报告", title), Spacer(1, 6 * mm)]
    summary = [
        ["工作单", content["workOrder"]["code"], "最终状态", content["workOrder"]["status"]],
        ["产品", content["workOrder"]["productCode"], "结论", content["outcome"]],
        [
            "SOP",
            f"{content['sop']['code']} / {content['sop']['version']}",
            "审计次数",
            str(len(content["audits"])),
        ],
    ]
    table = Table(summary, colWidths=[28 * mm, 57 * mm, 28 * mm, 48 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E5EEE9")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F5E8D5")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A8B2AA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 5 * mm), Paragraph("视频与模型追溯", heading)])
    for video in content["videos"]:
        story.append(
            Paragraph(f"{video['kind']} · {video['filename']} · SHA256 {video['sha256']}", body)
        )
    for index, audit in enumerate(content["audits"], start=1):
        story.extend(
            [
                Paragraph(f"审计 {index}: {audit['decision']}", heading),
                Paragraph(
                    f"{audit['provider']} / {audit['model']} / "
                    f"{audit['promptVersion']}<br/>{audit['summary']}",
                    body,
                ),
            ]
        )
        rows = [["步骤", "结果", "置信度", "时间", "证据"]]
        for finding in audit["findings"]:
            rows.append(
                [
                    str(finding["sequence"]),
                    finding["stepName"],
                    f"{'通过' if finding['detected'] else '未观察'} · {finding['confidence']}%",
                    f"{finding['startSeconds']} - {finding['endSeconds']}",
                    Paragraph(finding["evidence"], body),
                ]
            )
        detail = Table(rows, colWidths=[10 * mm, 32 * mm, 30 * mm, 24 * mm, 65 * mm], repeatRows=1)
        detail.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24483A")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BCC5BF")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([Spacer(1, 2 * mm), detail])
    if content["humanDecision"]:
        decision = content["humanDecision"]
        story.extend(
            [
                Paragraph("人工决定", heading),
                Paragraph(
                    f"状态：{decision['status']}<br/>"
                    f"复核人：{decision['reviewedBy']}<br/>"
                    f"理由：{decision['reason'] or '无'}",
                    body,
                ),
            ]
        )
    if content["rework"]:
        rework = content["rework"]
        story.extend(
            [
                Paragraph("返工记录", heading),
                Paragraph(
                    f"负责人：{rework['assigneeId']}<br/>"
                    f"要求：{rework['instructions']}<br/>"
                    f"复核人：{rework['reviewedBy']}<br/>"
                    f"结论：{rework['reviewNotes'] or rework['status']}",
                    body,
                ),
            ]
        )
    document.build(story)
    return buffer.getvalue()


def get_or_create_report(session: Session, storage: FileStorage, work_order: WorkOrder) -> Report:
    existing = session.scalar(
        select(Report).where(Report.work_order_id == work_order.id).order_by(Report.version.desc())
    )
    if existing:
        return existing
    content = build_report_content(session, work_order)
    pdf = render_report_pdf(content)
    report = Report(
        work_order_id=work_order.id,
        version=1,
        content=content,
        pdf_storage_key=f"reports/{work_order.id}/v1.pdf",
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
    )
    storage.put(report.pdf_storage_key, pdf)
    session.add(report)
    session.commit()
    session.refresh(report)
    return report
