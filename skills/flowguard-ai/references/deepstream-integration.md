# Official DeepStream SOP integration

FlowGuard reuses the official DeepStream SOP service as an independent visual
inference component. It does not copy or modify the official
`sop-inference-bp` implementation.

## Adapter location

The integration is implemented in:

`flowguard-ai/apps/api/src/flowguard_api/infrastructure/ai/providers.py`

`DeepStreamInferenceAdapter`:

1. uploads the video to the service's `/v1/files` endpoint;
2. sends `/v1/chat/completions` with `input_video.file_id`;
3. requests `chunking_options.algorithm=ddm-net`;
4. reads `choices[0].chunk_metadata_list`;
5. maps each chunk's `chunk_idx`, `start_time`, `end_time`,
   `cv_boundary_score`, and `response` into `InferenceFinding`.

`flowguard_api/infrastructure/ai/factory.py` selects this adapter only when
`FLOWGUARD_INFERENCE_PROVIDER=deepstream`. `config.py` supplies
`FLOWGUARD_DEEPSTREAM_BASE_URL`, `FLOWGUARD_DEEPSTREAM_API_KEY`, and
`FLOWGUARD_DEEPSTREAM_TIMEOUT_SECONDS`.

## Ownership boundary

DeepStream owns temporal boundary detection and chunk-level visual observation.
FlowGuard owns SOP alignment, missing/misordered checks, evidence gates,
human review, exception/rework state, and reports. The DeepStream service must
remain unchanged for FlowGuard-specific business behavior.

The FlowGuard audit service invokes the adapter and then evaluates the
provider-neutral findings through its execution graph. The `overall_pass` value
in a DeepStream response is not a release decision.

## Runtime reality

The current FlowGuard Compose file does not launch `nvds-action-sop`. The
official service must be deployed separately and made reachable from the API
container. The current server configuration uses Step 5, so the DeepStream
path is an available integration path, not proof that DeepStream is running.

Before switching providers, verify:

- the official service health/metadata endpoint;
- the API container can resolve and reach `FLOWGUARD_DEEPSTREAM_BASE_URL`;
- the service accepts the file and chat payload shape above;
- a sample response contains chunk metadata with usable timestamps.

Do not confuse the local `deepstream-sop` Skill instructions with a runtime
dependency. The Skill guides the work; the HTTP service performs inference.

