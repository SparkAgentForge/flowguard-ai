from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowguard_api.config import get_settings
from flowguard_api.models import (
    AuditDecision,
    AuditFinding,
    SopStatus,
    SopVersion,
    VideoAsset,
    VideoAudit,
    VideoAuditStatus,
    WorkOrder,
)
from flowguard_api.services.video_inference import get_video_inference_adapter
from flowguard_api.storage import FileStorage


class InvalidVideoAudit(ValueError):
    pass


def execute_video_audit(
    session: Session,
    work_order: WorkOrder,
    video: VideoAsset,
    storage: FileStorage,
) -> VideoAudit:
    version = session.scalar(
        select(SopVersion)
        .options(selectinload(SopVersion.steps))
        .where(SopVersion.id == work_order.sop_version_id)
    )
    if version is None:
        raise InvalidVideoAudit("工作单关联的 SOP 版本不存在")
    if version.status != SopStatus.PUBLISHED:
        raise InvalidVideoAudit("只有已发布的 SOP 才能用于视频检测")

    result = get_video_inference_adapter().analyze(
        video.filename, storage.get(video.storage_key), list(version.steps)
    )
    if result.overall_pass:
        decision = AuditDecision.PASS
    elif any(
        not finding.detected
        and finding.confidence < get_settings().manual_review_confidence_threshold
        for finding in result.findings
    ):
        decision = AuditDecision.INSUFFICIENT_EVIDENCE
    else:
        decision = AuditDecision.VIOLATION

    audit = VideoAudit(
        work_order_id=work_order.id,
        video_id=video.id,
        status=VideoAuditStatus.COMPLETED,
        decision=decision,
        provider=result.provider,
        model_name=result.model_name,
        overall_pass=result.overall_pass,
        summary=result.summary,
        raw_response=result.raw_response,
    )
    steps_by_code = {step.code: step for step in version.steps}
    for finding in result.findings:
        step = steps_by_code.get(finding.step_code)
        if step is None:
            raise InvalidVideoAudit(f"推理结果包含未知步骤 {finding.step_code}")
        audit.findings.append(
            AuditFinding(
                sop_step_id=step.id,
                sequence=step.sequence,
                step_name=step.name,
                detected=finding.detected,
                confidence=finding.confidence,
                start_seconds=finding.start_seconds,
                end_seconds=finding.end_seconds,
                evidence=finding.evidence,
                frame_timestamps=finding.frame_timestamps,
            )
        )
    session.add(audit)
    session.flush()
    return audit
