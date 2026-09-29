# FlowGuard AI Skill Benchmark

This file records reproducible Skill-level checks. It is not a claim that a
particular model is accurate, and it must not be replaced by a success badge
without the underlying run evidence.

## Routing cases

| Case | Expected route | Expected behavior |
| --- | --- | --- |
| “检测这个视频是否符合已发布 SOP” | `flowguard-ai` | Discover health, select published SOP, audit, poll, return evidence |
| “部署并验收 FlowGuard” | `flowguard-ai` | Inspect project, check prerequisites, run bounded acceptance |
| “排查 Step 5 帧 URL 或 RustFS” | `flowguard-ai` | Read the Step 5/RustFS contract and inspect the configured runtime |
| “切换到官方 DeepStream SOP” | `flowguard-ai` + `deepstream-sop` boundary | Configure the adapter; keep business rules in FlowGuard |
| “写一个普通 FastAPI CRUD” | no match | Do not load this Skill |
| “部署 Step1X-3D” | no match | Do not load this Skill |

## Latest local run

Run these commands from the repository root and replace this section only
when the outputs are available:

```text
quick_validate_skill.sh       PASS (2026-09-29)
scan_skill.sh                 PASS
source/installed parity       PASS (resynced after documentation update)
shell syntax                  PASS
server acceptance             PASS: provider=stepfun, 30 paths / 34 operations
Mock end-to-end audit         PASS: SOP -> PASS, VIOLATION, INSUFFICIENT_EVIDENCE -> rework -> report
real Step 5 audit             COMPLETE: supplied Install_1.MP4, decision preserved as VIOLATION
real Step 5 rework audit      COMPLETE: supplied Install_3.MP4, decision preserved as VIOLATION
real media playback           PASS: API streams 206 byte ranges without public RustFS
PDF Step 5 page extraction    PASS: rendered page stored in RustFS and parsed from image input
Step Code verification        PASS: read-enabled server/API/Skill routing and idempotent review check
external SkillSpector scan    NOT RUN: external tool/report not present
detached signature            NOT RUN: owner signing key not present
```

A release may be called locally validated, but must not be called fully
verified while any required external/runtime row is `NOT RUN` or `FAIL`.
