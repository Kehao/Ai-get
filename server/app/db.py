"""应用唯一的 SQLite 连接（P7 持久化）。

库文件由 `config.SQLITE_PATH` 决定（默认 `server/data/ai-get.db`），所有表共用
一个库一个连接：WAL 模式下读写不互斥，线程安全由「单连接 + `check_same_thread=False`」
配合调用方串行化（FastAPI 的线程池 + 各仓库自己的锁）保证。

首次连接时按文件名序号执行 `server/schema/` 下的全部 DDL（`CREATE TABLE IF NOT
EXISTS`，幂等）；后续加表只需新增 schema 文件，连接层不用改。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from . import config

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    """取共享连接。惰性建连：首次使用时建目录、建表。"""
    global _conn
    with _lock:
        if _conn is None:
            path = config.SQLITE_PATH
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # 查询返回可按列名索引的行，水合代码直接 dict(row)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            for schema_file in sorted(_SCHEMA_DIR.glob("0*.sql")):
                conn.executescript(schema_file.read_text(encoding="utf-8"))
            conn.commit()
            _conn = conn
        return _conn


def reset_connection() -> None:
    """仅供测试使用：丢弃当前连接，下次使用时按（可能已改的）配置重开。"""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
