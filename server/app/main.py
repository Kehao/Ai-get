"""Ai-get 后端服务入口。

只做装配：创建应用、挂载 CORS 与路由、注册全局异常处理、配置启动参数。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import SERVICE_NAME, SERVICE_VERSION
from .providers import SourceError, SourceErrorKind
from .routers import api_router

_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

# 数据源错误 → HTTP 语义的映射。
#
# 用全局异常处理器而不是在每个路由里写 try/except：新增爬虫能力时**不需要改任何路由**，
# 只要它按契约抛 `SourceError`，到这里就会得到正确的状态码。
#
# 另一条同样重要的约束：数据源失败**绝不能被降级成空结果**。返回 200 + 空列表会让
# 用户以为「市场上没有这类企业」，而事实是「这次没查到」。所以这里一律给 4xx/5xx。
_SOURCE_ERROR_STATUS: dict[SourceErrorKind, int] = {
    "missing_credentials": status.HTTP_503_SERVICE_UNAVAILABLE,
    "auth_failed": status.HTTP_502_BAD_GATEWAY,
    "permission_denied": status.HTTP_502_BAD_GATEWAY,
    "quota_exhausted": status.HTTP_402_PAYMENT_REQUIRED,
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "invalid_request": status.HTTP_400_BAD_REQUEST,
    "not_implemented": status.HTTP_501_NOT_IMPLEMENTED,
    "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "upstream_unavailable": status.HTTP_502_BAD_GATEWAY,
    "invalid_response": status.HTTP_502_BAD_GATEWAY,
}


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

    @app.exception_handler(SourceError)
    async def handle_source_error(_request: Request, error: SourceError) -> JSONResponse:
        headers = {"Retry-After": str(int(error.retry_after))} if error.retry_after else None
        return JSONResponse(
            status_code=_SOURCE_ERROR_STATUS.get(error.kind, status.HTTP_502_BAD_GATEWAY),
            content={
                "detail": f"数据源调用失败：{error}",
                "error_kind": error.kind,
                "retryable": error.retryable,
                "source_id": error.source_id,
            },
            headers=headers,
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}

    return app


app = create_app()
