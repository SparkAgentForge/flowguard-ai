# Runtime video audit workflow

This is the end-user path. The input is a video supplied to the AI tool and a
request such as “检测这个视频是否符合操作规范”. The output is an evidence-backed
FlowGuard decision, not a free-form visual opinion.

## 1. Discover the runtime

Use this order of precedence for the API base URL:

1. An explicit URL supplied by the user;
2. `FLOWGUARD_BASE_URL` or an existing project `.env`;
3. a FlowGuard checkout found from the current directory or its parents;
4. the local default `http://localhost:8000` only after checking it.

Inspect without changing state:

```bash
curl --fail --silent "$BASE_URL/api/v1/health"
docker compose ps
docker compose config --services
```

The health response must have `status: "ok"`. Record the reported
`inference_provider`; it determines whether Step 5 or DeepStream is used.

## 2. Prepare a missing or unhealthy FlowGuard

Only do this when the user asked to perform the audit and no usable service is
available. Prefer a checkout already present on the machine. Otherwise use the
configured repository URL, or:

```text
https://github.com/SparkAgentForge/flowguard-ai.git
```

Clone into a new, explicit project directory such as
`<user-selected-directory>/flowguard-ai`. If the user did not choose a
directory, use `~/.local/share/flowguard-ai` only when that path does not exist
or is empty. Before cloning, verify that the target does not contain unrelated
files. Never overwrite a directory, run a broad recursive delete, or modify
another Compose project.

Then:

```bash
docker compose -f <project>/compose.yaml config
docker compose -f <project>/compose.yaml up -d
```

Wait for PostgreSQL and RustFS health, then API health and Web availability.
Read the project `.env.example` and report missing model credentials or other
configuration. Docker image pulls and project-local builds are part of starting
the requested FlowGuard stack; system package installation is not. If Docker,
Compose, FFmpeg, or a required external model endpoint is absent, report the
exact prerequisite and stop.

Do not use `docker compose down -v` during a normal audit. It removes the
PostgreSQL, RustFS, and upload volumes. Do not stop services that are already
being used by another project.

## 3. Resolve the SOP

Call:

```text
GET /api/v1/sop-versions
```

Only published SOP versions are valid for an audit. If the list is empty, ask
the user to upload the operation manual. Do not create an SOP by guessing from
the uploaded video.

If the user supplies a manual, use this sequence:

```text
POST /api/v1/documents
POST /api/v1/documents/{document_id}/extract
PUT  /api/v1/sop-versions/{version_id}
POST /api/v1/sop-versions/{version_id}/submit-review
POST /api/v1/sop-versions/{version_id}/approve
POST /api/v1/sop-versions/{version_id}/publish
```

Publishing is a human gate. If the user has not approved the generated SOP,
stop and ask for that approval. When several published SOPs match, ask the
user to select one rather than silently selecting by list order.

## 4. Submit and monitor the video

Create a work order bound to the selected SOP, then upload and inspect:

```text
POST /api/v1/work-orders
POST /api/v1/work-orders/{work_order_id}/videos
POST /api/v1/work-orders/{work_order_id}/inspect
```

Save all IDs from each response. The inspect request is idempotent for a video
that is already `PROCESSING` or `COMPLETED`: do not submit another inspection
just because the client request timed out.

When the request returns or times out, read:

```text
GET /api/v1/work-orders/{work_order_id}/audits
GET /api/v1/work-orders/{work_order_id}/audits/{audit_id}
```

Poll a `PROCESSING` audit at a bounded interval. Stop polling after a practical
timeout and report that the server is still processing; include the audit ID so
the user can continue later. If it becomes `FAILED`, show the sanitized error
summary and check service logs/health before retrying.

## 5. Interpret the result

Use FlowGuard's decision and evidence fields:

- `PASS`: required steps have ordered, timestamped evidence;
- `VIOLATION`: required steps are missing or misordered;
- `INSUFFICIENT_EVIDENCE`: evidence is uncertain, occluded, or needs human
  review.

Report, in order:

1. overall decision and short summary;
2. each required step's evidence status and time range;
3. missing, misordered, or uncertain steps;
4. candidate/confirmed evidence clip links when present;
5. the next action: human review, exception confirmation, rework, or release.

Never infer that an earlier step happened only because the final product is
assembled. Provider `overall_pass` and confidence are advisory; the FlowGuard
execution graph is authoritative.

When the standalone Agent UI is deployed, return a single result-page URL after
the relevant API IDs are known. Use the configured `FLOWGUARD_AGENT_WEB_URL`
without adding authentication or share tokens:

```text
PASS or INSUFFICIENT_EVIDENCE:
  {FLOWGUARD_AGENT_WEB_URL}/audit/{work_order_id}/{audit_id}
VIOLATION:
  {FLOWGUARD_AGENT_WEB_URL}/exception/{exception_id}
Published SOP preview:
  {FLOWGUARD_AGENT_WEB_URL}/sop/{version_id}
Archived report:
  {FLOWGUARD_AGENT_WEB_URL}/report/{work_order_id}
```

The Agent UI is a read-oriented presentation surface. Only its exception page
may perform the configured confirmation and rework actions; the management
workbench remains the full administrative interface.

## 6. Rework path

For a confirmed exception:

```text
POST /api/v1/exceptions/{exception_id}/confirm
POST /api/v1/exceptions/{exception_id}/rework-task
POST /api/v1/rework-tasks/{task_id}/videos
POST /api/v1/rework-tasks/{task_id}/review
```

A passing rework audit releases the work order. A failed or uncertain rework
audit returns it to the appropriate human/rework state. Link the re-audit
result instead of claiming that uploading a rework video alone passed it.

## 7. Cleanup and reporting

Do not delete user data after a normal audit. Generate a report only when the
work order is in a reportable state:

```text
GET /api/v1/reports/{work_order_id}
GET /api/v1/reports/{work_order_id}/pdf
```

For an explicitly requested test run, clean only objects and records created by
that run. Never remove PostgreSQL/RustFS volumes or unrelated projects.
