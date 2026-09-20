"""数据源结果的 SQLite TTL 缓存（P7）。

真实数据源按次计费，**同一企业的查询结果必须缓存**：TTL 内重复命中零成本，
进程重启后缓存依然有效（跨会话去重扣费）。本模块刻意做成与具体数据源无关的
通用件——`get/set/clear` 三个函数的签名与语义与旧的进程内字典版本完全一致，
三个 adapter（tavily/baidu/pdl）没有做过任何改动。

存储介质：共享连接 `app.db`（`source_cache` 表，DDL 真源在
`server/schema/001_source_cache.sql`）。值用 pickle 存 BLOB——缓存对象是本地
代码自己写入的（dataclass/dict/str），不存在反序列化不可信数据的场景；类型保真
免去了为 CompanyRecord 手写编解码器。TTL（默认 7 天）天然限制了旧代码 pickle 的
存活期，代码变更后最多一个 TTL 内自然淘汰；读侧再加一层防御，损坏的行直接按
miss 处理。

容量上限是防膨胀的兜底：超过 `_MAX_ENTRIES` 时先清过期行，仍超则删最旧的
`_PRUNE_COUNT` 行——缓存 miss 的代价只是一次重新计费。
"""

from __future__ import annotations

import pickle
import sqlite3
import time

from .. import config
from .. import db

_MAX_ENTRIES = 10_000
_PRUNE_COUNT = 1_000


def get(key: str) -> object | None:
    """取缓存值；不存在、过期或损坏返回 None。

    「缓存了空结果」由调用方的值语义承载（如各源缓存的空串哨兵），
    本层不区分 miss 与空结果——与旧进程内版本对调用方的可见行为一致。
    """
    row = _fetch(key)
    if row is None:
        return None
    try:
        return pickle.loads(row)
    except Exception:  # noqa: BLE001 — 旧代码的 pickle 无法还原时按 miss 处理并清除
        conn = db.connect()
        with conn:
            conn.execute("DELETE FROM source_cache WHERE cache_key = ?", (key,))
        return None


def set(key: str, value: object, *, ttl_seconds: int | None = None) -> None:
    """写入缓存。None 也会被如实缓存（get 回 None）——与旧版本语义一致。"""
    if ttl_seconds is None:
        ttl_seconds = config.SOURCE_CACHE_TTL_SECONDS
    now = int(time.time())
    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO source_cache (cache_key, source_id, value, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, key.split(":", 1)[0], pickle.dumps(value), now, now + ttl_seconds),
        )
        _prune_if_needed(conn)


def clear() -> None:
    """仅供测试使用。"""
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM source_cache")


def _fetch(key: str) -> bytes | None:
    """取未过期的 value；顺手删掉已过期行（读写同表，原子性由共享锁保证）。"""
    conn = db.connect()
    row = conn.execute(
        "SELECT value, expires_at FROM source_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    value, expires_at = row
    if expires_at < time.time():
        with conn:
            conn.execute("DELETE FROM source_cache WHERE cache_key = ?", (key,))
        return None
    return bytes(value)


def _prune_if_needed(conn: sqlite3.Connection) -> None:
    """超过容量上限：先清过期行，仍超则删最旧的 _PRUNE_COUNT 行。"""
    count = conn.execute("SELECT COUNT(*) FROM source_cache").fetchone()[0]
    if count < _MAX_ENTRIES:
        return
    conn.execute("DELETE FROM source_cache WHERE expires_at < ?", (int(time.time()),))
    count = conn.execute("SELECT COUNT(*) FROM source_cache").fetchone()[0]
    if count >= _MAX_ENTRIES:
        conn.execute(
            "DELETE FROM source_cache WHERE cache_key IN"
            " (SELECT cache_key FROM source_cache ORDER BY created_at LIMIT ?)",
            (_PRUNE_COUNT,),
        )
