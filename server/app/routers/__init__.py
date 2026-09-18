"""路由聚合。main 只负责装配，不直接定义接口。"""

from __future__ import annotations

from fastapi import APIRouter

from . import agents, auth, connect, knowledge, opportunities, research, settings, targets

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(targets.router)
api_router.include_router(research.router)
api_router.include_router(agents.router)
api_router.include_router(connect.router)
api_router.include_router(knowledge.router)
api_router.include_router(opportunities.router)
api_router.include_router(settings.router)

__all__ = ["api_router"]
