# FlowGuard architecture and ownership

## Dependency direction

```text
routes -> services/application -> core contracts
                              ^
                    infrastructure adapters
```

- `flowguard_api/application.py` assembles FastAPI, middleware, and routes.
- `flowguard_api/core/` contains provider-neutral contracts such as
  `VideoInferenceAdapter`, `InferenceResult`, `InferenceFinding`, and
  `FileStorage`.
- `flowguard_api/infrastructure/database/` contains PostgreSQL/SQLAlchemy
  setup and request-scoped database dependencies.
- `flowguard_api/infrastructure/storage/` contains local and RustFS/S3 storage
  implementations.
- `flowguard_api/infrastructure/ai/` contains Mock, Step 5, document vision,
  and DeepStream adapters.
- `flowguard_api/services/` owns SOP workflow, execution graph, video audit,
  rework, and reporting. Routes should not call provider SDKs directly.

## Provider matrix

| Provider | Input | Owns | Selected by |
| --- | --- | --- | --- |
| `mock` | non-empty video bytes | deterministic demo findings | default local demo |
| `stepfun` | RustFS-stored frames sent as base64 data URLs | Step 5 visual observations | `FLOWGUARD_INFERENCE_PROVIDER=stepfun` |
| `deepstream` | uploaded video file ID | GEBD/DDM chunks and VLM observations | `FLOWGUARD_INFERENCE_PROVIDER=deepstream` |

All providers return the `InferenceResult` contract. The audit service then
calls the execution graph and stores the raw provider response together with
the normalized findings. Provider output never directly releases a work order.

## Business gates

The reviewed SOP is immutable after publication; changes create a new version.
The work order binds one published version. The audit evaluates required and
optional steps, sequence, evidence score, timestamps, and uncertainty. An
uncertain required step creates a targeted review request. Confirmed violations
can create a rework task. A rework review runs the same SOP and only a passing
result releases the work order. Reports are generated from database facts and
retain model/provider metadata and evidence references.

## Current project facts

- PostgreSQL is the only supported database for the application and tests.
- RustFS is the object-storage system for manuals, frames, videos, and report
  artifacts.
- `compose.yaml` starts API, Web, PostgreSQL, RustFS, and its permissions job;
  it does not start `nvds-action-sop`.
- The server's current deployment uses Step 5 unless its environment is
  explicitly changed. A separate Step1X-3D service is unrelated to this
  architecture.
