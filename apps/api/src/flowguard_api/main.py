from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flowguard_api.config import get_settings
from flowguard_api.routes.health import router as health_router
from flowguard_api.routes.reports import router as reports_router
from flowguard_api.routes.sops import router as sops_router
from flowguard_api.routes.video_audits import router as video_audits_router
from flowguard_api.routes.work_orders import router as work_orders_router
from flowguard_api.routes.workflow import router as workflow_router


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
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(reports_router, prefix=settings.api_prefix)
    app.include_router(sops_router, prefix=settings.api_prefix)
    app.include_router(video_audits_router, prefix=settings.api_prefix)
    app.include_router(work_orders_router, prefix=settings.api_prefix)
    app.include_router(workflow_router, prefix=settings.api_prefix)
    return app


app = create_app()
