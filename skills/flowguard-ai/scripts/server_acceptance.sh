#!/usr/bin/env bash
set -euo pipefail

base_url="${FLOWGUARD_BASE_URL:-http://localhost:8000}"
base_url="${base_url%/}"
timeout_seconds="${FLOWGUARD_ACCEPTANCE_TIMEOUT_SECONDS:-15}"
auth_args=()

if [[ -n "${FLOWGUARD_BASIC_AUTH_USER:-}" || -n "${FLOWGUARD_BASIC_AUTH_PASSWORD:-}" ]]; then
  if [[ -z "${FLOWGUARD_BASIC_AUTH_USER:-}" || -z "${FLOWGUARD_BASIC_AUTH_PASSWORD:-}" ]]; then
    printf '%s\n' "Basic Auth 需要同时提供 FLOWGUARD_BASIC_AUTH_USER 和 FLOWGUARD_BASIC_AUTH_PASSWORD。" >&2
    exit 2
  fi
  auth_args=(-u "${FLOWGUARD_BASIC_AUTH_USER}:${FLOWGUARD_BASIC_AUTH_PASSWORD}")
fi

get_url() {
  if ((${#auth_args[@]})); then
    curl --fail --silent --show-error --max-time "$timeout_seconds" \
      --retry 1 --retry-delay 1 "${auth_args[@]}" "$1"
  else
    curl --fail --silent --show-error --max-time "$timeout_seconds" \
      --retry 1 --retry-delay 1 "$1"
  fi
}

health_json="$(get_url "$base_url/api/v1/health")"
python3 - "$health_json" "${FLOWGUARD_EXPECTED_PROVIDER:-}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("status") != "ok":
    raise SystemExit(f"API health status is not ok: {payload!r}")
expected = sys.argv[2]
if expected and payload.get("inference_provider") != expected:
    raise SystemExit(
        f"provider mismatch: expected {expected!r}, got {payload.get('inference_provider')!r}"
    )
print(
    "API healthy: "
    f"{payload.get('service', 'unknown')} / provider={payload.get('inference_provider', 'unknown')}"
)
PY

openapi_json="$(get_url "$base_url/api/openapi.json")"
python3 - "$openapi_json" <<'PY'
import json
import sys

paths = set(json.loads(sys.argv[1]).get("paths", {}))
required = {
    "/api/v1/work-orders/{work_order_id}/videos",
    "/api/v1/work-orders/{work_order_id}/inspect",
    "/api/v1/exceptions/{exception_id}/confirm",
    "/api/v1/reports/{work_order_id}/pdf",
}
missing = sorted(required - paths)
if missing:
    raise SystemExit(f"OpenAPI 缺少 FlowGuard 核心接口: {missing}")
print(f"OpenAPI verified: {len(paths)} paths")
PY

if [[ -n "${FLOWGUARD_WEB_URL:-}" ]]; then
  if ((${#auth_args[@]})); then
    curl --fail --silent --show-error --max-time "$timeout_seconds" \
      --retry 1 --retry-delay 1 "${auth_args[@]}" "${FLOWGUARD_WEB_URL%/}/" >/dev/null
  else
    curl --fail --silent --show-error --max-time "$timeout_seconds" \
      --retry 1 --retry-delay 1 "${FLOWGUARD_WEB_URL%/}/" >/dev/null
  fi
  printf 'Web endpoint healthy: %s\n' "${FLOWGUARD_WEB_URL%/}"
fi

if [[ -n "${FLOWGUARD_RUSTFS_URL:-}" ]]; then
  curl --fail --silent --show-error --max-time "$timeout_seconds" \
    --retry 1 --retry-delay 1 "${FLOWGUARD_RUSTFS_URL%/}/health" >/dev/null
  printf 'RustFS endpoint healthy: %s\n' "${FLOWGUARD_RUSTFS_URL%/}"
fi

if [[ -n "${FLOWGUARD_DEEPSTREAM_URL:-}" ]]; then
  deepstream_url="${FLOWGUARD_DEEPSTREAM_URL%/}/v1/metadata"
  if ! curl --fail --silent --show-error --max-time "$timeout_seconds" \
    --retry 1 --retry-delay 1 "$deepstream_url" >/dev/null; then
    if [[ "${FLOWGUARD_REQUIRE_DEEPSTREAM:-0}" == "1" ]]; then
      printf 'DeepStream metadata check failed: %s\n' "$deepstream_url" >&2
      exit 1
    fi
    printf 'Warning: DeepStream metadata check failed: %s\n' "$deepstream_url" >&2
  else
    printf 'DeepStream metadata endpoint healthy: %s\n' "$deepstream_url"
  fi
fi

if [[ "${FLOWGUARD_RUN_PROJECT_SMOKE:-0}" == "1" ]]; then
  project_root="${FLOWGUARD_PROJECT_ROOT:-}"
  if [[ -z "$project_root" || ! -f "$project_root/scripts/integration_smoke.py" ]]; then
    printf '%s\n' "FLOWGUARD_RUN_PROJECT_SMOKE=1 时必须提供有效的 FLOWGUARD_PROJECT_ROOT。" >&2
    exit 2
  fi
  (
    cd "$project_root"
    FLOWGUARD_SMOKE_BASE_URL="$base_url" \
      FLOWGUARD_SMOKE_USERNAME="${FLOWGUARD_BASIC_AUTH_USER:-}" \
      FLOWGUARD_SMOKE_PASSWORD="${FLOWGUARD_BASIC_AUTH_PASSWORD:-}" \
      python3 scripts/integration_smoke.py
  )
fi

printf '%s\n' "Health/OpenAPI acceptance passed. The business flow is intentionally not mutated by this script."
printf '%s\n' "Use references/acceptance-matrix.md for the manual -> SOP -> audit -> rework -> report run, then clean only test artifacts."
