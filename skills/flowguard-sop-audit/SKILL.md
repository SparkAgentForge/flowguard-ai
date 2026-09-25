---
name: flowguard-sop-audit
description: Convert DeepStream SOP chunks and Step 5 visual observations into an auditable, execution-graph-based SOP decision with evidence gates and targeted human review. Use for FlowGuard video audits; do not use for generic video understanding or camera control.
metadata:
  short-description: Auditable SOP evidence decisions
---

# FlowGuard SOP Audit

Use this skill when implementing or reviewing FlowGuard's fixed-workcell video
audit. The input may come from the NVIDIA DeepStream SOP microservice (GEBD
boundaries plus chunk metadata) or Step 5. The output is a provider-neutral
finding list and a deterministic decision.

## Boundary

- DeepStream owns temporal segmentation; do not duplicate GEBD or modify the
  official `sop-inference-bp` implementation for FlowGuard business rules.
- Step 5 owns visual descriptions; it must not release a work order by itself.
- FlowGuard owns the reviewed SOP execution graph, order checks, evidence gates,
  exception state, human review, rework, and the immutable report.
- This skill is for pre-recorded fixed-workcell videos. It does not authorize
  camera control, PLC commands, identity recognition, or physical torque
  inference.

## Decision contract

1. Normalize each observation to `step_code`, `detected`, confidence/evidence
   score, time range, frame timestamps, and optional `occluded`/chunk metadata.
2. Align observed events to the reviewed SOP sequence and preconditions.
3. Return exactly one of `PASS`, `VIOLATION`, or `INSUFFICIENT_EVIDENCE`.
4. Missing or misordered required steps are `VIOLATION` only when the video has
   enough evidence to make that claim. Occlusion, absent timestamps, empty
   evidence, or low confidence produce `INSUFFICIENT_EVIDENCE` and a targeted
   review request.
5. Optional steps do not block a pass, but remain visible in the trace.

Read the focused references when changing the contract:

- [Execution graph](references/execution-graph.md)
- [Evidence contract](references/evidence-contract.md)
- [Review policy](references/review-policy.md)

Use `scripts/validate_audit_result.py` for fixture checks before changing API
serialization or provider adapters.
