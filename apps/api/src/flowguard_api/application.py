"""FlowGuard application bootstrap and composition root.

This module assembles the HTTP application and its routers.  It deliberately
does not contain business rules or infrastructure implementations; those are
provided by the routes, services, and infrastructure packages respectively.
"""

import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from flowguard_api.config import get_settings
from flowguard_api.infrastructure.database.migrations import upgrade_database
from flowguard_api.routes.health import router as health_router
from flowguard_api.routes.reports import router as reports_router
from flowguard_api.routes.sops import router as sops_router
from flowguard_api.routes.video_audits import router as video_audits_router
from flowguard_api.routes.work_orders import router as work_orders_router
from flowguard_api.routes.workflow import router as workflow_router

logger = logging.getLogger("flowguard.api")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": message, "code": code},
        headers=headers,
    )


def _http_error_defaults(status_code: int) -> tuple[str, str]:
    defaults = {
        400: ("BAD_REQUEST", "请求内容有误，请检查后重试。"),
        401: ("UNAUTHORIZED", "当前操作需要登录后才能继续。"),
        403: ("FORBIDDEN", "当前操作没有权限。"),
        404: ("NOT_FOUND", "找不到对应资源，请刷新页面后重试。"),
        405: ("METHOD_NOT_ALLOWED", "当前操作不受支持，请检查请求方式。"),
        409: ("DATA_CONFLICT", "数据已发生变化，请刷新页面后重试。"),
        413: ("PAYLOAD_TOO_LARGE", "提交内容超过大小限制，请选择更小的文件。"),
        415: ("UNSUPPORTED_MEDIA_TYPE", "文件格式不受支持，请检查后重试。"),
        422: ("VALIDATION_ERROR", "请求参数有误，请检查填写内容后重试。"),
        429: ("TOO_MANY_REQUESTS", "请求过于频繁，请稍后重试。"),
        503: ("SERVICE_UNAVAILABLE", "服务暂时不可用，请稍后重试。"),
    }
    return defaults.get(status_code, ("HTTP_ERROR", "请求未完成，请稍后重试。"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError):
        logger.info("请求参数校验失败: %s %s", request.method, request.url.path)
        return _error_response(422, "VALIDATION_ERROR", "请求参数有误，请检查填写内容后重试。")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException):
        default_code, default_message = _http_error_defaults(error.status_code)
        # Route-level details are deliberately user-facing; hide unexpected
        # 5xx details so internal provider/database messages never leak.
        route_message = error.detail if isinstance(error.detail, str) else ""
        message = (
            route_message
            if error.status_code < 500
            and route_message not in {"", "Not Found", "Method Not Allowed"}
            else default_message
        )
        code = default_code
        logger.info(
            "请求被拒绝: %s %s status=%s code=%s",
            request.method,
            request.url.path,
            error.status_code,
            code,
        )
        return _error_response(error.status_code, code, message, error.headers)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, error: IntegrityError):
        logger.exception("数据库约束冲突: %s %s", request.method, request.url.path)
        return _error_response(409, "DATA_CONFLICT", "数据已存在或与现有记录冲突，请刷新后重试。")

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, error: SQLAlchemyError):
        logger.exception("数据库操作失败: %s %s", request.method, request.url.path)
        return _error_response(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用，请稍后重试。")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception):
        logger.exception("未处理的服务异常: %s %s", request.method, request.url.path)
        return _error_response(500, "INTERNAL_ERROR", "服务暂时无法完成请求，请稍后重试。")

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(reports_router, prefix=settings.api_prefix)
    app.include_router(sops_router, prefix=settings.api_prefix)
    app.include_router(video_audits_router, prefix=settings.api_prefix)
    app.include_router(work_orders_router, prefix=settings.api_prefix)
    app.include_router(workflow_router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    """Start the HTTP server when the application module is executed directly."""

    settings = get_settings()
    upgrade_database()
    uvicorn.run(
        "flowguard_api.application:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    run()
