"""L0 标准的 LLM 生成入口。

这一层**刻意不认识业务模型**：它只负责「调用、缓存、统计、报错」，
返回的是原始 dict 列表。把 dict 变成 `Criterion` 的校验与构造放在
`qualification/criteria.py`——那里才是 schema 的所有者。

这样分层的好处是校验规则的单一来源：新增一个维度只需要改 `criteria.py`，
不需要动 LLM 层。

## 缓存

键是 `(prompt_version, model, 画像正文, 用户手写条件)` 的哈希。命中缓存时**不产生外部调用**。

注意缓存与「结果冻结」是两个不同层次的东西：
- **缓存**解决「同样的输入重复问」——纯省钱，可丢弃。
- **冻结**解决「同一个任务不能中途换标准」——写在任务记录里，不可丢弃。

两者都需要，不能互相替代。
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from .client import Completion, LlmError, complete_json
from .config import get_settings
from .prompts import load_asset, render_user_prompt

# 缓存容量。以画像正文为键，条目极小，留足空间避免在演示中反复重新调用。
_CACHE_CAPACITY = 128


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """一次 L0 生成的产物与元信息，供调用方写入任务记录以实现可追溯。"""

    criteria: tuple[dict, ...]
    prompt_version: str
    model: str
    total_tokens: int
    cached: bool


@dataclass
class GenerationStats:
    """可观测性计数。没有它就无法回答「LLM 到底省了多少次调用」。"""

    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    total_tokens: int = 0
    last_error_kind: str = ""
    last_error_message: str = ""

    def describe(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "failures": self.failures,
            "total_tokens": self.total_tokens,
            "cache_size": len(_cache),
            "last_error_kind": self.last_error_kind,
            "last_error_message": self.last_error_message,
        }


_cache: "OrderedDict[str, tuple[dict, ...]]" = OrderedDict()
_lock = threading.RLock()
_stats = GenerationStats()


def generate_criteria(text: str, user_conditions: tuple[str, ...] = (), mode: str = "company") -> GenerationResult:
    """调用 LLM 产出标准 dict 列表。任何失败都抛 `LlmError`，由调用方决定怎么降级。

    `mode` 决定读哪份契约（会社 / 人物）——两份契约各有版本号，
    缓存键里含版本，所以两种模式天然不串缓存。
    """
    settings = get_settings()
    # 提示词来自技能目录，加载失败会抛 PromptAssetError（属于部署错误，不该被当成 LLM 抖动掩盖）。
    asset = load_asset(mode)
    key = _cache_key(asset.version, text, user_conditions, settings.model)

    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            _stats.cache_hits += 1
            return GenerationResult(
                criteria=hit,
                prompt_version=asset.version,
                model=settings.model,
                total_tokens=0,
                cached=True,
            )

    try:
        completion: Completion = complete_json(
            asset.system,
            render_user_prompt(text, user_conditions, mode),
            temperature=0.0,
        )
    except LlmError as error:
        with _lock:
            _stats.failures += 1
            _stats.last_error_kind = error.kind
            _stats.last_error_message = str(error)[:200]
        raise

    raw_items = completion.data.get("criteria")
    if not isinstance(raw_items, list):
        raise LlmError("LLM 返回体缺少 criteria 数组", kind="invalid_response")

    criteria = tuple(item for item in raw_items if isinstance(item, dict))
    if not criteria:
        raise LlmError("LLM 返回的 criteria 为空", kind="invalid_response")

    with _lock:
        _stats.calls += 1
        _stats.total_tokens += completion.total_tokens
        _cache[key] = criteria
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_CAPACITY:
            _cache.popitem(last=False)

    return GenerationResult(
        criteria=criteria,
        prompt_version=asset.version,
        model=completion.model or settings.model,
        total_tokens=completion.total_tokens,
        cached=False,
    )


def stats() -> GenerationStats:
    return _stats


def reset() -> None:
    """仅供测试：清空缓存与计数。"""
    with _lock:
        _cache.clear()
        global _stats
        _stats = GenerationStats()


def _cache_key(prompt_version: str, text: str, user_conditions: tuple[str, ...], model: str) -> str:
    material = "\x1f".join([prompt_version, model, text.strip(), *user_conditions])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
