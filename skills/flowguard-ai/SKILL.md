---
name: flowguard-ai
description: >
  Use when building, deploying, evaluating, debugging, or documenting the
  open-source FlowGuard AI project: SOP ingestion, Step 5/RustFS visual
  analysis, DeepStream SOP integration, audit decisions, rework verification,
  report archival, or server acceptance. Do not use for unrelated FastAPI
  work, generic video editing, or Step1X-3D deployment.
metadata:
  short-description: FlowGuard AI delivery and acceptance workflow
  domain: industrial-video-agent
  version: "1.0.0"
---

# FlowGuard AI

This skill governs the complete open-source FlowGuard AI project. It is an
orchestration skill: it connects the reviewed SOP, visual inference providers,
the execution graph, human gates, rework, and the final evidence package. It is
not a replacement for the official NVIDIA `deepstream-sop` skill or the
official `sop-inference-bp` implementation.

## Instructions

1. Establish the current state before changing anything. Inspect the repository,
   active provider, compose services, migrations, and relevant server state.
   Preserve unrelated user changes. Read only the references needed for the
   requested mode.
2. Keep the provider boundary explicit:
   - DeepStream SOP owns GEBD/DDM temporal chunking and visual chunk
     observations.
   - Step 5 owns visual understanding of manual pages and extracted video
     frames.
   - FlowGuard owns the reviewed SOP execution graph, evidence gates, sequence
     decisions, exception state, human review, rework, and immutable reports.
3. For Step 5 PDF or video work, persist images to RustFS before sending a
   request. Send only Step 5-reachable presigned URLs, retain object keys in
   the audit record, and keep internal and public object-storage endpoints
   separate. Never silently fall back to inline frame bytes or an inaccessible
   localhost URL.
4. For DeepStream work, call the unchanged official service through
   `DeepStreamInferenceAdapter`. Use its `/v1/files` and
   `/v1/chat/completions` contract and map `chunk_metadata_list` to the
   provider-neutral finding contract. Do not add FlowGuard business rules to
   `sop-inference-bp`.
5. Recompute the business decision in FlowGuard. A provider `overall_pass` is
   advisory only. Missing, misordered, low-confidence, occluded, or untimed
   evidence must remain a violation or targeted human-review request according
   to the execution graph; do not infer an unseen action from the final product
   state.
6. Treat the end-to-end path as the acceptance target:
   manual upload -> SOP extraction -> review -> publish -> work order -> video
   audit -> evidence/decision -> exception -> rework -> re-audit -> report.
   Preserve the real UUIDs and status transitions from every response.
7. When deploying or testing a server, use explicit user-provided endpoints
   and credentials. Do not write secrets into the repository, skill files,
   logs, screenshots, or reports. Do not install missing dependencies
   automatically; report the exact prerequisite and wait for the environment
   owner to install it.
8. Limit remote mutations to the FlowGuard project and to resources created by
   the current test. Never delete PostgreSQL/RustFS data volumes or unrelated
   services. After a test, remove only its temporary uploads, frame objects,
   and generated artifacts, and report what was cleaned up.
9. Before claiming success, run static skill validation and the smallest useful
   acceptance checks. If a check fails, record the failing request, provider,
   service, and root cause, make the narrowest correction, redeploy only when
   explicitly authorized, and repeat the failed check.

## Reference routing

- Read [project-scope.md](references/project-scope.md) for the open-source
  project scope, supported deployment assumptions, and safety boundaries.
- Read [flowguard-architecture.md](references/flowguard-architecture.md) when
  changing application boundaries, provider contracts, or workflow states.
- Read [deepstream-integration.md](references/deepstream-integration.md) when
  using, deploying, or debugging the official DeepStream SOP service.
- Read [step5-rustfs-contract.md](references/step5-rustfs-contract.md) for PDF
  page and video-frame URL handling.
- Read [deployment-runbook.md](references/deployment-runbook.md) for local or
  server deployment, prerequisites, and cleanup rules.
- Read [acceptance-matrix.md](references/acceptance-matrix.md) for the full
  business-flow test and expected statuses/API calls.

The repository's `flowguard-sop-audit` skill remains the focused decision
contract for evidence normalization and execution-graph evaluation. Load it
when changing that contract; this skill supplies the project-level
orchestration around it.

## Examples

- "Deploy and accept the FlowGuard AI project on the supplied server."
- "Trace why Step 5 frame analysis fails after RustFS upload."
- "Switch the audit provider to the official DeepStream SOP service and verify
  chunk evidence without moving business logic into DeepStream."
- "Run the manual -> SOP -> video -> exception -> rework -> report acceptance
  path and clean up only test artifacts."
