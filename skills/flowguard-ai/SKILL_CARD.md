# FlowGuard AI Skill Card

## Identity

| Field | Value |
| --- | --- |
| Name | `flowguard-ai` |
| Version | `1.0.0` |
| Scope | FlowGuard SOP video audit and the runtime lifecycle required to perform it |
| Primary entry | Natural-language request with a video and an SOP context |
| Explicit entry | `$flowguard-ai` |

## User promise

The Skill discovers or prepares a FlowGuard runtime, verifies that a published
SOP is available, runs an evidence-backed video audit, and returns the decision,
step evidence, uncertainty, and next action. It does not replace human review
when evidence is missing or ambiguous.

## Required inputs

- Audit: video, published SOP/version or a manual to create one, and a local
  target or API base URL.
- Maintenance: target checkout or endpoint, requested operation, and any
  provider choice that cannot be discovered safely.
- Remote credentials: environment variables or an existing credential helper;
  never chat text, checked-in files, logs, or screenshots.

The Skill asks for missing or ambiguous values before changing state or
starting an expensive inference call.

## Safety boundaries

- Only mutate the FlowGuard project and resources created by the current run.
- Never overwrite a non-empty checkout, unrelated Compose stack, PostgreSQL
  data volume, RustFS data volume, or checked-in configuration.
- Never print, persist, or commit secrets, private keys, bearer tokens, or
  signed URL query strings.
- Never treat a provider's `overall_pass` as the FlowGuard business decision.
- Missing external verification or signing evidence is reported explicitly.

## Evidence map

| Gate | Evidence in this repository | External/runtime evidence |
| --- | --- | --- |
| Cataloged | `agents/openai.yaml`, `references/api-catalog.md` | Product catalog or registry record |
| Scanned | `scripts/quick_validate_skill.sh`, `scripts/scan_skill.sh` | SkillSpector/security scan report |
| Evaluated | `BENCHMARK.md`, `references/acceptance-matrix.md` | Server acceptance run and benchmark artifacts |
| Signed | `scripts/sign_skill_manifest.sh` | Detached `skill.oms.sig` made with owner key |
| Documented | This card, `SKILL.md`, reference manuals | User-facing release notes or trust record |

## Verification status

The local structural and safety checks are reproducible. Full verified status
requires the external scan report, a real runtime acceptance run, and an
owner-controlled detached signature. Those artifacts are intentionally not
fabricated or committed with the Skill.
