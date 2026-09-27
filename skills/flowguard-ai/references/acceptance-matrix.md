# End-to-end acceptance matrix

Use the API documentation in `flowguard-ai/docs/API.md` for the current request
schemas. Save IDs from each response; do not use example UUIDs.

| Stage | Request | Expected result |
| --- | --- | --- |
| Health | `GET /api/v1/health` and OpenAPI | API is healthy; provider is known |
| Manual upload | `POST /api/v1/documents` | Document record and SHA256 |
| SOP extraction | `POST /api/v1/documents/{id}/extract` | `AI_EXTRACTED` candidate with source refs |
| SOP review | `PUT /api/v1/sop-versions/{id}` and submit-review | Edited candidate reaches `IN_REVIEW` |
| SOP publish | approve then publish | Immutable `PUBLISHED` version |
| Work order | `POST /api/v1/work-orders` | `CREATED`, bound to the published version |
| Normal video | upload then `POST /inspect` | `PASS`/verified path with findings and execution trace |
| Exception video | upload missing/occluded sample then inspect | `VIOLATION` or `INSUFFICIENT_EVIDENCE` with exception/review request |
| Human gate | confirm/reject exception | State changes only through the documented gate |
| Rework | create task, upload rework video | Task and work order enter rework-submitted state |
| Rework review | `POST /rework-tasks/{id}/review` | Passing rework becomes `RELEASED`; failing rework returns to assignment |
| Report | JSON report then PDF | Archived report contains SOP, hashes, audits, findings, and human decisions |

## Minimum scenarios

1. Normal pass: manual -> published SOP -> `normal.mp4` -> audit -> report.
2. Confirmed violation: `missing-step.mp4` -> exception confirm -> rework ->
   `rework-normal.mp4` -> review -> release -> report.
3. Insufficient evidence: `occluded.mp4` -> targeted review request; no
   automatic release based only on a confidence number.

## Provider checks

For `mock`, use the repository's deterministic filename fixtures. For `stepfun`,
verify RustFS object keys and Base64 data URLs without storing image bytes in
the audit record. For `deepstream`,
verify the official service response includes chunk metadata and that FlowGuard
stores chunk fields in findings before the execution graph evaluates them.

## Failure record

For every failed stage record:

- run ID and endpoint (without credentials or signed URL query strings);
- HTTP status and sanitized error detail;
- provider/model and service health;
- created object keys or database IDs;
- root cause and narrow correction;
- second-run result and cleanup status.
