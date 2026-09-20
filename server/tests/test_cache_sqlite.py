"""SQLite 源缓存的单元测试。

conftest 已把缓存库指到 :memory:；持久化语义（跨连接存活）单独用 tmp_path 文件库验证。
"""

from __future__ import annotations

import time
from pathlib import Path

from app.providers import cache as source_cache
from app.providers.contracts import CompanyRecord, Evidence
from app import db


def test_roundtrip_dataclass():
    record = CompanyRecord(
        external_id="tavily-yunshan.net",
        name="云杉网络",
        domain="yunshan.net",
        industries=("云安全",),
        summary="企业云安全服务商",
        evidence=(Evidence(title="t", url="https://yunshan.net", snippet="s"),),
        missing_fields=frozenset({"contacts"}),
        source_id="tavily",
    )
    source_cache.set("k", record)
    loaded = source_cache.get("k")
    assert loaded == record  # tuple / frozenset / 嵌套 Evidence 全部保真
    assert isinstance(loaded.industries, tuple)
    assert isinstance(loaded.missing_fields, frozenset)


def test_empty_string_sentinel_passes_through():
    """各源用空串表示「确认过没有」：缓存层必须原样存取，不能当成 miss。"""
    source_cache.set("empty", "")
    assert source_cache.get("empty") == ""


def test_none_is_cached_as_none():
    source_cache.set("none", None)
    assert source_cache.get("none") is None


def test_missing_key_returns_none():
    assert source_cache.get("never-set") is None


def test_expiry_returns_none():
    source_cache.set("stale", "v", ttl_seconds=0)
    time.sleep(0.01)
    assert source_cache.get("stale") is None  # 过期行被顺手删除
    assert source_cache.get("stale") is None  # 再次读取仍是 miss，不报错


def test_clear_removes_all():
    source_cache.set("a", "1")
    source_cache.set("b", "2")
    source_cache.clear()
    assert source_cache.get("a") is None
    assert source_cache.get("b") is None


def test_persists_across_reconnection(monkeypatch):
    """P7 核心语义：换一个连接（模拟进程重启）后缓存仍然命中。

    用项目目录下的临时库而非 pytest tmp_path——沙箱环境会拦 tmp_path 的目录创建。
    """
    db_file = Path(__file__).resolve().parent / ".cache_persist_test.db"
    monkeypatch.setattr("app.config.SQLITE_PATH", str(db_file))
    db.reset_connection()
    try:
        source_cache.set("persist", {"hello": "世界"})
        db.reset_connection()  # 丢掉连接 ≈ 进程重启
        assert source_cache.get("persist") == {"hello": "世界"}
    finally:
        db.reset_connection()
        db_file.unlink(missing_ok=True)
