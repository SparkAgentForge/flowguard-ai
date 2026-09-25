"""Deterministic SOP execution graph and evidence decisioning.

The visual provider reports observations. This module owns the business
interpretation of those observations so a model cannot directly release a
work order.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import inf
from typing import Any

from flowguard_api.models import SopStep


@dataclass(frozen=True)
class ObservedEvent:
    step_code: str
    start_seconds: int | None
    end_seconds: int | None
    confidence: int
    evidence: str
    frame_timestamps: list[int]
    occluded: bool = False


@dataclass(frozen=True)
class AlignmentItem:
    expected_code: str
    observed_code: str | None
    status: str
    reason: str


@dataclass(frozen=True)
class EvidenceEvaluation:
    decision: str
    overall_pass: bool
    summary: str
    missing_steps: list[str]
    misordered_steps: list[str]
    uncertain_steps: list[str]
    trace: list[AlignmentItem]
    review_requests: list[dict[str, Any]]


def compile_execution_graph(steps: Iterable[SopStep]) -> dict[str, Any]:
    """Compile the reviewed SOP rows into a serializable execution graph."""
    ordered = sorted(steps, key=lambda item: item.sequence)
    return {
        "schema_version": "1.0",
        "nodes": [
            {
                "code": step.code,
                "sequence": step.sequence,
                "name": step.name,
                "required": step.required,
                "preconditions": list(step.preconditions or []),
                "evidence_requirements": list(step.evidence_requirements or []),
                "on_missing": step.on_missing,
            }
            for step in ordered
        ],
        "edges": [
            {"from": ordered[index - 1].code, "to": step.code, "type": "required_before"}
            for index, step in enumerate(ordered)
            if index > 0
        ],
    }


def _event_from_finding(finding: Any) -> ObservedEvent:
    return ObservedEvent(
        step_code=finding.step_code,
        start_seconds=finding.start_seconds,
        end_seconds=finding.end_seconds,
        confidence=finding.confidence,
        evidence=finding.evidence,
        frame_timestamps=list(finding.frame_timestamps),
        occluded=bool(getattr(finding, "occluded", False)),
    )


def _align(steps: list[SopStep], events: list[ObservedEvent]) -> list[AlignmentItem]:
    expected = sorted(steps, key=lambda item: item.sequence)
    observed = sorted(
        (event for event in events if event.start_seconds is not None),
        key=lambda event: (event.start_seconds if event.start_seconds is not None else inf),
    )
    expected_index = {step.code: index for index, step in enumerate(expected)}
    consumed: set[str] = set()
    cursor = 0
    result: list[AlignmentItem] = []

    for event in observed:
        index = expected_index.get(event.step_code)
        if index is None:
            continue
        if event.step_code in consumed:
            result.append(
                AlignmentItem(
                    event.step_code, event.step_code, "DUPLICATE", "同一动作在视频中重复出现"
                )
            )
            continue
        if index < cursor:
            result.append(
                AlignmentItem(
                    event.step_code, event.step_code, "MISORDERED", "动作出现在其前置步骤之后"
                )
            )
            consumed.add(event.step_code)
            continue
        if index > cursor:
            for missing in expected[cursor:index]:
                if missing.code not in consumed:
                    result.append(
                        AlignmentItem(
                            missing.code,
                            None,
                            "MISSING",
                            f"在观察到 {event.step_code} 前未观察到该步骤",
                        )
                    )
                    consumed.add(missing.code)
        result.append(
            AlignmentItem(event.step_code, event.step_code, "MATCHED", "按 SOP 顺序观察到")
        )
        consumed.add(event.step_code)
        cursor = max(cursor, index + 1)

    for step in expected:
        if step.code not in consumed:
            result.append(AlignmentItem(step.code, None, "MISSING", "整段视频中没有可用动作证据"))
    return result


def evaluate_evidence(
    steps: Iterable[SopStep],
    findings: Iterable[Any],
    manual_review_threshold: int = 60,
) -> EvidenceEvaluation:
    """Fuse model observations with the reviewed execution graph."""
    ordered_steps = sorted(steps, key=lambda item: item.sequence)
    finding_list = list(findings)
    by_code = {finding.step_code: finding for finding in finding_list}
    events = [_event_from_finding(finding) for finding in finding_list if finding.detected]
    alignment = _align(ordered_steps, events)
    alignment_by_code = {item.expected_code: item for item in alignment}
    missing: list[str] = []
    misordered: list[str] = []
    uncertain: list[str] = []
    review_requests: list[dict[str, Any]] = []

    for step in ordered_steps:
        finding = by_code.get(step.code)
        item = alignment_by_code.get(step.code)
        if finding is None:
            if step.required:
                missing.append(step.code)
            continue
        if item and item.status in {"MISORDERED", "DUPLICATE"}:
            if step.required:
                misordered.append(step.code)
            continue
        if not finding.detected:
            if not step.required:
                continue
            if finding.confidence < manual_review_threshold:
                uncertain.append(step.code)
                review_requests.append(
                    _review_request(step, finding, "未能确认该步骤，模型证据不足")
                )
            else:
                missing.append(step.code)
            continue
        if (
            finding.occluded
            or finding.confidence < manual_review_threshold
            or not finding.evidence.strip()
            or not finding.frame_timestamps
            or finding.start_seconds is None
            or finding.end_seconds is None
        ):
            uncertain.append(step.code)
            review_requests.append(_review_request(step, finding, "动作区域遮挡或证据不完整"))

    if uncertain:
        decision = "INSUFFICIENT_EVIDENCE"
        summary = f"{len(uncertain)} 个步骤证据不足，需要定向复核"
    elif missing or misordered:
        decision = "VIOLATION"
        reasons = []
        if missing:
            reasons.append(f"缺失 {', '.join(missing)}")
        if misordered:
            reasons.append(f"错序 {', '.join(misordered)}")
        summary = "；".join(reasons)
    else:
        decision = "PASS"
        summary = "所有必需步骤均已按顺序观察到，证据满足要求"

    return EvidenceEvaluation(
        decision=decision,
        overall_pass=decision == "PASS",
        summary=summary,
        missing_steps=missing,
        misordered_steps=misordered,
        uncertain_steps=uncertain,
        trace=alignment,
        review_requests=review_requests,
    )


def _review_request(step: SopStep, finding: Any, reason: str) -> dict[str, Any]:
    start = finding.start_seconds if finding.start_seconds is not None else 0
    end = finding.end_seconds if finding.end_seconds is not None else start + 6
    return {
        "id": f"review-{step.code}-{start}",
        "step_code": step.code,
        "step_name": step.name,
        "start_seconds": start,
        "end_seconds": end,
        "question": (
            f"请确认“{step.name}”是否满足："
            f"{'；'.join(step.evidence_requirements or ['动作清晰可见'])}"
        ),
        "reason": reason,
        "status": "PENDING",
    }


def evaluation_to_dict(evaluation: EvidenceEvaluation) -> dict[str, Any]:
    payload = asdict(evaluation)
    payload["trace"] = [asdict(item) for item in evaluation.trace]
    return payload
