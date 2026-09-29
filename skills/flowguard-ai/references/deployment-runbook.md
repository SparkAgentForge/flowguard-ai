# Deployment and server runbook

This runbook is for an explicit local or server deployment request. It does
not authorize remote access, package installation, destructive cleanup, or
service shutdown by itself.

## Preflight

Inspect before changing anything:

```bash
git -C flowguard-ai status --short
docker compose -f flowguard-ai/compose.yaml config
```

Verify that the target host has the required Docker runtime, PostgreSQL/RustFS
access, FFmpeg/ffprobe for Step 5 or DeepStream, and the configured model
endpoint. If a dependency is missing, report it and let the environment owner
install it. Do not download it automatically.

Never copy `.env`, passwords, API keys, model weights, or private access
workbooks into the Skill or commit them to Git.

## Compose services

The FlowGuard Compose stack contains:

- `api` (default port 8000);
- `web` (default port 5173);
- `agent-web` (default port 5174, standalone AI result pages);
- `postgres` (loopback port 5432);
- `rustfs` (S3 port 9000 and loopback console port 9001);
- `rustfs-permissions` (one-shot volume permission setup).

The official DeepStream service is a separate stack. Keep its base URL in the
API environment rather than adding FlowGuard rules to its container.

## Safe deployment sequence

1. Confirm the intended checkout and inspect uncommitted changes.
2. Transfer only the requested project files through the user-approved channel.
3. Validate the resolved Compose file and environment without printing secrets.
4. Build or restart only the requested FlowGuard services.
5. Wait for PostgreSQL and RustFS health, then API health and Web availability.
6. Run static checks and the acceptance matrix.
7. Record provider, model, image tags, endpoint names, and failures without
   recording credentials.

Health alone does not verify playback: request a stored video's content with
`Range: bytes=0-1023` and require a `206` response and `Content-Range`. The
browser should reach only the API, not a private/public RustFS redirect.
Verify FFmpeg inside the actual API image, including custom deployment
Dockerfiles. A host binary does not make it available inside the container.

Use `scripts/acceptance_workflow.py` from the project checkout only against an
explicitly isolated test API/database/bucket. Mock mode checks state branches;
real mode preserves the observed model decision. Neither health checks nor
Mock PASS results establish real-world recognition accuracy. If a long model
call exceeds the client/proxy timeout, preserve its audit ID and poll instead
of submitting another inference request.

Do not use `git reset --hard`, broad recursive deletion, or volume deletion.
Do not stop an existing service after testing unless the user explicitly asks.

## Cleanup

Use a unique test-run prefix for uploaded documents, videos, frame objects,
and generated reports where the API permits it. At the end, delete only those
test artifacts and temporary directories. Keep user data, PostgreSQL data, and
RustFS data volumes. Report cleanup failures instead of widening the deletion
scope.
