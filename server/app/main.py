"""Ai-get 后端服务入口。

只做装配：创建应用、挂载 CORS 与路由、配置启动参数。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import SERVICE_NAME, SERVICE_VERSION
from .routers import api_router

_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def create_app() -> FastAPI:
    app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}

    return app


app = create_app()
