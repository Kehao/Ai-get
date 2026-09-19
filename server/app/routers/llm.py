"""LLM 接入状态接口。

存在的理由是**可观测性**：标准生成有两条路径（LLM 优先、规则兜底），
降级是静默的——任务照样建得出来，只是标准质量不同。没有这个接口，
「为什么这次的标准和上次不一样」就只能靠翻日志。

这里只读不写：LLM 的开关在 `server/.env` 里，改配置需要重启进程，
不提供一个「运行时能改密钥」的接口——那会把密钥带进请求体与访问日志。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import llm
from ..deps import current_user
from ..models import LlmRounds, LlmStatus, User

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status", response_model=LlmStatus)
def read_llm_status(user: User = Depends(current_user)) -> LlmStatus:
    settings = llm.get_settings()
    counts = llm.stats()
    return LlmStatus(
        enabled=settings.enabled,
        configured=settings.configured,
        usable=settings.usable,
        model=settings.model,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        max_tokens=settings.max_tokens,
        judge_enabled=settings.judge_enabled,
        prompt_version=llm.prompt_version(),
        prompt_dir=llm.prompt_dir_label(),
        rounds=LlmRounds(**counts.describe()),
    )
