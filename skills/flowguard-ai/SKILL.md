---
name: flowguard-ai
description: >
  Use when a user asks an AI tool to check an uploaded video against an SOP
  using FlowGuard AI, or when deploying, evaluating, debugging, or maintaining
  the FlowGuard runtime. Discover or prepare the local FlowGuard service,
  verify a published SOP, upload and audit the video, and return evidence and
  next actions. Do not use for unrelated FastAPI work, generic video editing,
  or Step1X-3D deployment.
metadata:
  short-description: FlowGuard AI delivery and acceptance workflow
  domain: industrial-video-agent
  version: "1.0.0"
---

# FlowGuard AI

This is a user-facing runtime skill for SOP video auditing. When a user uploads
a video and asks whether it follows an operation standard, the agent uses this
skill to find or prepare FlowGuard, check the service, select a published SOP,
run the audit, and explain the evidence-backed result. It also contains the
maintenance path for building, deploying, evaluating, and debugging FlowGuard.

The skill has one narrow responsibility: orchestrate a FlowGuard SOP audit and
its runtime lifecycle. The endpoint catalog is a routing aid, not an invitation
to expose every FlowGuard feature in every request.

It is not a replacement for the official NVIDIA `deepstream-sop` skill or the
official `sop-inference-bp` implementation.

## Instructions

### Routing and preflight

Use this skill only when the request is about FlowGuard SOP auditing, or about
deploying, evaluating, debugging, or documenting that runtime. Do not use it
for generic FastAPI CRUD, ordinary video editing, Step1X-3D, or an unrelated
model service.

Before a state-changing or expensive operation, collect all missing required
parameters in one short question. Never guess them:

- an audit needs the video, the published SOP/version (or a manual to create
  one), and the target FlowGuard base URL or permission to discover/prepare a
  local checkout;
- a maintenance request needs the target checkout or endpoint, the requested
  operation, and any provider choice that is not discoverable from health or
  configuration;
- remote deployment, deletion, cleanup, and provider changes require explicit
  user intent; credentials must be supplied through the environment, never in
  a prompt, source file, or log.

If a value can be read safely from the local project or a health response,
read it. If it is ambiguous, ask instead of selecting a default that changes
behavior. Reuse an existing health result, SOP selection, or audit ID within
the same run; do not repeat an expensive model call merely to refresh context.

### Runtime video audit

When the request is to check a user-provided video, follow
[runtime-audit-workflow.md](references/runtime-audit-workflow.md). The short
sequence is:

1. Locate an existing FlowGuard checkout and determine its API base URL from
   the current project, environment, or user-provided endpoint.
2. Check `GET /api/v1/health`, Docker Compose service state, and OpenAPI. If
   FlowGuard is absent or unhealthy, prepare it before auditing: use the
   configured repository URL or the public
   `https://github.com/SparkAgentForge/flowguard-ai.git`, clone only into an
   explicit empty/new directory, start only its Compose stack, and wait for
   PostgreSQL, RustFS, API, and Web health. Never overwrite an existing
   directory or unrelated Compose project.
3. Query published SOP versions. If none exists, ask the user for the
   operation manual; do not invent an SOP from the video. If several SOPs are
   possible and the user did not identify one, ask them to choose.
4. Upload the video, call the inspect endpoint, and preserve the returned
   `work_order_id`, `video_id`, and `audit_id`. If the request times out while
   the audit is `PROCESSING`, poll the audit list/detail endpoint instead of
   submitting a duplicate request.
5. Return the decision, summary, step timeline, missing/misordered or uncertain
   steps, evidence clip links when available, and the next action. A model
   confidence or provider `overall_pass` is never enough to release a work
   order.

Do not silently change the user's video, SOP, checked-in configuration, or
service configuration. Ask before choosing among ambiguous SOPs or before
destructive cleanup. If a required dependency is missing (Docker, Compose,
FFmpeg, database, object storage, or model credentials), report the exact
prerequisite and stop at that stage; do not install system packages without
explicit user authorization.

### Project maintenance

For development, deployment, evaluation, debugging, or documentation, first
establish the current state. Inspect the repository, active provider, Compose
services, migrations, and relevant server state. Preserve unrelated user
changes. Read only the references needed for the requested mode.

Keep the provider boundary explicit:
1. DeepStream SOP owns GEBD/DDM temporal chunking and visual chunk
   observations.
2. Step 5 owns visual understanding of manual pages and extracted video
   frames.
3. FlowGuard owns the reviewed SOP execution graph, evidence gates, sequence
   decisions, exception state, human review, rework, and immutable reports.
4. For Step 5 PDF or video work, persist images to RustFS before sending a
   request. Send image bytes as base64 data URLs in the model request and
   retain object keys in the audit record. The model must not need to fetch
   RustFS objects; keep browser-preview URLs separate from the AI request.
5. For DeepStream work, call the unchanged official service through
   `DeepStreamInferenceAdapter`. Use its `/v1/files` and
   `/v1/chat/completions` contract and map `chunk_metadata_list` to the
   provider-neutral finding contract. Do not add FlowGuard business rules to
   `sop-inference-bp`.
6. Recompute the business decision in FlowGuard. A provider `overall_pass` is
   advisory only. Missing, misordered, low-confidence, occluded, or untimed
   evidence must remain a violation or targeted human-review request according
   to the execution graph; do not infer an unseen action from the final product
   state.
7. Treat the end-to-end path as the acceptance target:
   manual upload -> SOP extraction -> review -> publish -> work order -> video
   audit -> evidence/decision -> exception -> rework -> re-audit -> report.
   Preserve the real UUIDs and status transitions from every response.
8. When deploying or testing a server, use explicit user-provided endpoints
   and credentials. Do not write secrets into the repository, skill files,
   logs, screenshots, or reports. Do not install missing dependencies
   automatically; report the exact prerequisite and wait for the environment
   owner to install it.
9. Limit remote mutations to the FlowGuard project and to resources created by
   the current test. Never delete PostgreSQL/RustFS data volumes or unrelated
   services. After a test, remove only its temporary uploads, frame objects,
   and generated artifacts, and report what was cleaned up.
10. Before claiming success, run static skill validation and the smallest useful
   acceptance checks. If a check fails, record the failing request, provider,
   service, and root cause, make the narrowest correction, redeploy only when
   explicitly authorized, and repeat the failed check.

### Verified-skill evidence

Treat the five gates in [verification.md](references/verification.md) as a
release contract:

`Cataloged + Scanned + Evaluated + Signed + Documented`.

The repository contains the catalog, local scan, benchmark record, Skill Card,
and a detached-signature workflow. Do not claim the Skill is fully verified
unless an external scan report and an owner-controlled signature are also
present. A missing external artifact is a reported gap, not a reason to invent
an attestation.

## Reference routing

- Read [runtime-audit-workflow.md](references/runtime-audit-workflow.md) for the
  end-user upload -> environment discovery -> SOP -> audit -> result flow.
- Read [api-catalog.md](references/api-catalog.md) as the endpoint operation
  manual when selecting or explaining a FlowGuard interface.
- Read [verification.md](references/verification.md) when packaging, scanning,
  evaluating, signing, or declaring the Skill verified.
- Read [SKILL_CARD.md](SKILL_CARD.md) for the user-facing trust record and
  [BENCHMARK.md](BENCHMARK.md) for the latest local evaluation record.

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

The API implementation and its tests are the source of truth for evidence
normalization and execution-graph evaluation. The Skill only orchestrates the
runtime and explains the returned decision; it does not replace the server's
business logic.

## Examples

- "Deploy and accept the FlowGuard AI project on the supplied server."
- "Trace why Step 5 frame analysis fails after RustFS upload."
- "Switch the audit provider to the official DeepStream SOP service and verify
  chunk evidence without moving business logic into DeepStream."
- "Run the manual -> SOP -> video -> exception -> rework -> report acceptance
  path and clean up only test artifacts."
