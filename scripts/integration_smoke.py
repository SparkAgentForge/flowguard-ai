import base64
import json
import os
import urllib.error
import urllib.request


def get_json(url: str) -> dict:
    request = urllib.request.Request(url)
    username = os.environ.get("FLOWGUARD_SMOKE_USERNAME")
    password = os.environ.get("FLOWGUARD_SMOKE_PASSWORD")
    if username and password:
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, urllib.error.URLError) as error:
        raise SystemExit(f"请求失败: {url}: {error}") from error


base_url = os.environ.get("FLOWGUARD_SMOKE_BASE_URL", "http://localhost:8000")
health = get_json(f"{base_url}/api/v1/health")
assert health["status"] == "ok", health
openapi = get_json(f"{base_url}/api/openapi.json")
paths = openapi["paths"]
required = {
    "/api/v1/work-orders/{work_order_id}/videos",
    "/api/v1/work-orders/{work_order_id}/inspect",
    "/api/v1/exceptions/{exception_id}/confirm",
    "/api/v1/reports/{work_order_id}/pdf",
}
missing = sorted(required - paths.keys())
if missing:
    raise SystemExit(f"OpenAPI 缺少接口: {missing}")
print(f"FlowGuard smoke test passed: {health['service']} with {len(paths)} API paths")
