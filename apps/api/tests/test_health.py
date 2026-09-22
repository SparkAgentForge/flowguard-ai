from fastapi.testclient import TestClient

from flowguard_api.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "flowguard-api",
        "environment": "development",
        "inference_provider": "mock",
    }
