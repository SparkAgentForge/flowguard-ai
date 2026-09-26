from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from flowguard_api.application import create_app


def test_unexpected_error_returns_safe_user_message() -> None:
    app = create_app()

    @app.get("/test/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError("database password must never be returned")

    response = TestClient(app, raise_server_exceptions=False).get("/test/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "服务暂时无法完成请求，请稍后重试。",
        "code": "INTERNAL_ERROR",
    }
    assert "password" not in response.text


def test_database_constraint_error_returns_conflict_message() -> None:
    app = create_app()

    @app.get("/test/integrity-error")
    def integrity_error() -> None:
        raise IntegrityError("insert", {}, RuntimeError("constraint details"))

    response = TestClient(app, raise_server_exceptions=False).get("/test/integrity-error")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "数据已存在或与现有记录冲突，请刷新后重试。",
        "code": "DATA_CONFLICT",
    }


def test_unknown_route_returns_structured_chinese_message() -> None:
    response = TestClient(create_app()).get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "找不到对应资源，请刷新页面后重试。",
        "code": "NOT_FOUND",
    }
