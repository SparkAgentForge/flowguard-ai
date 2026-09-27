# FlowGuard AI project scope

FlowGuard AI is an open-source quality-assistance and fixed-workcell process
audit project. This reference defines the supported product boundary; it is
not a product launch plan, event brief, or vendor entitlement statement.

## Supported workflow

- Import an operation manual and produce an editable candidate SOP.
- Require human review before publishing an immutable SOP version.
- Bind a published SOP to a work order.
- Analyze a recorded workcell video with Mock, Step 5, or the official
  DeepStream SOP service.
- Normalize visual observations into auditable evidence.
- Detect missing, misordered, low-confidence, or occluded steps.
- Request human review, create a rework task, and re-audit a submitted rework
  video.
- Archive a report containing source hashes, provider metadata, evidence, and
  human decisions.

## Deployment assumptions

- PostgreSQL is the production database. Do not add a SQLite fallback.
- RustFS is the object store for manuals, pages, frames, videos, and report
  artifacts.
- Docker Compose provides the API, Web, PostgreSQL, RustFS, and RustFS
  permissions services.
- The official DeepStream SOP service is an independent deployment. It is not
  modified to contain FlowGuard business rules.
- Step 5 requires a reachable object-storage URL for every image it receives.

## Non-goals and safety boundaries

- This project does not control PLCs or production lines.
- This project does not identify people or infer identity.
- This project does not estimate physical parameters that are not directly
  visible in the supplied evidence.
- A model confidence or provider `overall_pass` cannot release a work order by
  itself; the FlowGuard execution graph and required human gates remain
  authoritative.
- Missing local dependencies must be reported to the environment owner rather
  than installed automatically by the Skill.

## Source material

- Product scenario: `flowguard-ai/docs/检测.md`
- Requirements: `flowguard-ai/docs/需求文档.md`
- Architecture: `flowguard-ai/docs/技术架构.md`
- API contract: `flowguard-ai/docs/API.md`
- Official DeepStream reference: `sop-monitoring-blueprints/microservices/sop-inference-bp/`
