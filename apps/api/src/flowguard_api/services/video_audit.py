from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowguard_api.config import get_settings
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.ai.factory import get_video_inference_adapter
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
from flowguard_api.services.evidence_clips import EvidenceClipError, generate_evidence_clips
from flowguard_api.services.execution_graph import (
    compile_execution_graph,
    evaluate_evidence,
    evaluation_to_dict,
)


class InvalidVideoAudit(ValueError):
    pass


def execute_video_audit(
    session: Session,
    work_order: WorkOrder,
    video: VideoAsset,
    storage: FileStorage,
    audit: VideoAudit | None = None,
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

    result = get_video_inference_adapter(storage, work_order_id=work_order.id).analyze(
        video.filename, storage.get(video.storage_key), list(version.steps)
    )
    evaluation = evaluate_evidence(
        version.steps,
        result.findings,
        manual_review_threshold=get_settings().manual_review_confidence_threshold,
    )
    decision = AuditDecision(evaluation.decision)
    execution_trace = evaluation_to_dict(evaluation)
    execution_trace["graph"] = compile_execution_graph(version.steps)
    status_by_code: dict[str, str] = {}
    for item in evaluation.trace:
        if item.status == "MISSING":
            status_by_code.setdefault(item.expected_code, "MISSING")
        elif item.status == "MISORDERED":
            status_by_code[item.expected_code] = "MISORDERED"
        elif item.status == "MATCHED":
            status_by_code.setdefault(item.expected_code, "CONFIRMED")
    for code in evaluation.uncertain_steps:
        status_by_code[code] = "UNCERTAIN"

    if audit is None:
        audit = VideoAudit(
            work_order_id=work_order.id,
            video_id=video.id,
            status=VideoAuditStatus.COMPLETED,
            decision=decision,
            provider=result.provider,
            model_name=result.model_name,
            overall_pass=evaluation.overall_pass,
            summary=evaluation.summary,
            raw_response={
                **result.raw_response,
                "flowguard_evaluation": execution_trace,
            },
            execution_trace=execution_trace,
            review_requests=evaluation.review_requests,
        )
        session.add(audit)
    else:
        audit.status = VideoAuditStatus.COMPLETED
        audit.decision = decision
        audit.provider = result.provider
        audit.model_name = result.model_name
        audit.overall_pass = evaluation.overall_pass
        audit.summary = evaluation.summary
        audit.raw_response = {
            **result.raw_response,
            "flowguard_evaluation": execution_trace,
        }
        audit.execution_trace = execution_trace
        audit.review_requests = evaluation.review_requests
    steps_by_code = {step.code: step for step in version.steps}
    unknown_codes = set(finding.step_code for finding in result.findings) - set(steps_by_code)
    if unknown_codes:
        raise InvalidVideoAudit(f"推理结果包含未知步骤 {', '.join(sorted(unknown_codes))}")
    findings_by_code = {finding.step_code: finding for finding in result.findings}
    for step in sorted(version.steps, key=lambda item: item.sequence):
        finding = findings_by_code.get(step.code)
        evidence_status = status_by_code.get(step.code, "MISSING")
        if not step.required and finding is None:
            evidence_status = "SKIPPED"
        if finding is None:
            audit.findings.append(
                AuditFinding(
                    sop_step_id=step.id,
                    sequence=step.sequence,
                    step_name=step.name,
                    detected=False,
                    confidence=0,
                    evidence_status=evidence_status,
                    evidence_score=0,
                    occluded=False,
                    evidence="推理结果未返回该步骤的观察记录",
                    frame_timestamps=[],
                )
            )
            continue
        if not step.required and not finding.detected:
            evidence_status = "SKIPPED"
        # An uncertain observation must not look like a confirmed cut in the
        # audit timeline. Keep its candidate range separately for targeted
        # review and clip playback.
        display_times = evidence_status != "UNCERTAIN"
        candidate_evidence = evidence_status in {"UNCERTAIN", "MISSING", "MISORDERED"}
        audit.findings.append(
            AuditFinding(
                sop_step_id=step.id,
                sequence=step.sequence,
                step_name=step.name,
                detected=finding.detected,
                confidence=finding.confidence,
                evidence_status=evidence_status,
                evidence_score=(
                    finding.evidence_score
                    if finding.evidence_score is not None
                    else finding.confidence
                ),
                occluded=finding.occluded,
                chunk_idx=finding.chunk_idx,
                cv_boundary_score=finding.cv_boundary_score,
                start_seconds=finding.start_seconds if display_times else None,
                end_seconds=finding.end_seconds if display_times else None,
                candidate_start_seconds=(
                    finding.candidate_start_seconds
                    if candidate_evidence
                    else None
                ),
                candidate_end_seconds=(
                    finding.candidate_end_seconds if candidate_evidence else None
                ),
                evidence=finding.evidence,
                frame_timestamps=finding.frame_timestamps if display_times else [],
                candidate_frame_timestamps=(
                    (finding.candidate_frame_timestamps or finding.frame_timestamps)
                    if candidate_evidence
                    else []
                ),
            )
        )
    session.flush()
    clip_error: str | None = None
    try:
        evidence_clips = generate_evidence_clips(
            storage=storage,
            video=video,
            audit_id=audit.id,
            findings=audit.findings,
        )
    except EvidenceClipError as error:
        # An audit remains valid when a demo/mock video cannot be transcoded;
        # the finding timeline is still usable and the error is visible for
        # operators. Real Step 5 audits normally produce clips here.
        evidence_clips = {}
        clip_error = str(error)
    audit.raw_response = {
        **audit.raw_response,
        "evidence_clips": evidence_clips,
        **({"evidence_clip_error": clip_error} if clip_error else {}),
    }
    session.flush()
    return audit
