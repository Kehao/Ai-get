"""数据源结果的进程内 TTL 缓存。

真实数据源按次计费，**同一企业的查询结果必须缓存**：TTL 内重复命中零成本，
重复画像的重复挖掘也不再重复扣配额。这里刻意做成与具体数据源无关的通用件，
两个 adapter 都经由它读写；P7 的持久化缓存（SQLite）落地后，只需替换本模块
的实现而不用碰任何 adapter。

容量上限是防泄漏的兜底：进程内字典没有淘汰策略会无限增长，
超过上限时整体清空是可接受的粗粒度策略——缓存 miss 的代价只是一次重新计费。
"""

from __future__ import annotations

import threading
import time

from ..config import SOURCE_CACHE_TTL_SECONDS

_MAX_ENTRIES = 10_000

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def get(key: str) -> object | None:
    """取缓存值，过期或不存在返回 None（None 与「缓存了空结果」用 `_sentinel` 区分）。"""
    with _lock:
        entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < time.monotonic():
        with _lock:
            _cache.pop(key, None)
        return None
    return None if value is _sentinel else value


def set(key: str, value: object, *, ttl_seconds: int = SOURCE_CACHE_TTL_SECONDS) -> None:
    """写入缓存。`value` 为 None 时缓存「确认过没有」的空结果，避免反复查询空档企业。"""
    with _lock:
        if len(_cache) >= _MAX_ENTRIES:
            _cache.clear()
        _cache[key] = (time.monotonic() + ttl_seconds, _sentinel if value is None else value)


def clear() -> None:
    """仅供测试使用。"""
    with _lock:
        _cache.clear()


class _Sentinel:
    """占位类型：区分「没缓存过」与「缓存了空结果」。"""

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return "<empty>"


_sentinel = _Sentinel()
