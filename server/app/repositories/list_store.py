"""挖掘列表状态的 SQLite 持久化（P7 第二步）。

`TargetListRepository` 的 `_ListState` 原本是纯内存单例，进程重启即失。
本模块把状态写穿（write-through）到 `mining_lists` / `mining_rows` 两张表，
启动时水合（hydrate）回内存——对所有调用方（路由、分页、导出）零感知。

## 序列化分工

- **pydantic 模型**（TargetList / TargetCompany / TargetPerson / TargetColumn /
  OutreachPlan / condition_items / strategy_groups）：`model_dump_json` 往返；
- **dataclass**（Criterion / Judgment / CompanyRecord / PersonRecord）：
  `app.serialize` 按注解编解码（tuple / frozenset / 嵌套 Evidence 保真）。

## 与 targets.py 的循环依赖

`_ListState`、`_apply_progress` 定义在 targets.py，而 targets.py 需要在模块级
import 本模块做写穿——所以水合所需的两个符号在函数体内**局部导入**，
`_row_key` / `_record_key` / `_seed_from` 三个小工具则按同口径本地复制。

## 崩溃语义

`running` 状态的列表在水合时统一按 `completed` 处理：行已经全部判定完成
（判定在创建时同步做完），中断的只是前端进度动画——假装「还在跑」只会让
进度条卡死在 99%。
"""

from __future__ import annotations

import json
import time
import zlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .. import db, serialize
from ..models import (
    OutreachPlan,
    StrategyGroup,
    TargetColumn,
    TargetCompany,
    TargetCondition,
    TargetList,
    TargetPerson,
)
from ..providers.contracts import CompanyRecord, PersonRecord
from ..qualification.criteria import Criterion
from ..qualification.scoring import Judgment

if TYPE_CHECKING:
    from .targets import _ListState

RowT = TargetCompany | TargetPerson


def save(state: "_ListState") -> None:
    """把一份 `_ListState` 写穿到库（UPSERT 列表 + 整体替换行）。"""
    tl = state.target_list
    now = int(time.time())
    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO mining_lists"
            " (id, query, mode, status, progress, requested_count, discovered_count,"
            "  contact_count, seed, condition_items_json, strategy_groups_json,"
            "  criteria_json, columns_json, follow_up_plan_json, outreach_json,"
            "  recall_source_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tl.id,
                tl.query,
                tl.mode,
                tl.status,
                tl.progress,
                tl.requested_count,
                tl.discovered_count,
                tl.contact_count,
                _seed_from(tl.id),
                json.dumps(
                    [item.model_dump(mode="json") for item in tl.condition_items],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [item.model_dump(mode="json") for item in tl.strategy_groups],
                    ensure_ascii=False,
                ),
                serialize.dumps(list(state.criteria)),
                json.dumps([item.model_dump(mode="json") for item in state.columns], ensure_ascii=False),
                tl.follow_up_plan,
                state.outreach.model_dump_json() if state.outreach else None,
                tl.source_id,
                int(tl.created_at.timestamp()),
                now,
            ),
        )
        conn.execute("DELETE FROM mining_rows WHERE list_id = ?", (tl.id,))
        for row in state.rows:
            record = state.records.get(_row_key(row))
            judgment = state.judgments.get(row.id)
            conn.execute(
                "INSERT OR REPLACE INTO mining_rows"
                " (row_id, list_id, dedupe_key, row_json, record_json, judgment_json,"
                "  score, verdict, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.id,
                    tl.id,
                    _row_key(row) if isinstance(row, TargetCompany) else "",
                    row.model_dump_json(),
                    serialize.dumps(record) if record is not None else "{}",
                    serialize.dumps(judgment) if judgment is not None else "null",
                    float(judgment.score) if judgment is not None else 0.0,
                    row.match_level,
                    int(row.created_at.timestamp()),
                ),
            )


def delete(list_id: str) -> None:
    """删除列表及其全部行（外键 CASCADE 已兜底，显式删一遍更直观）。"""
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM mining_rows WHERE list_id = ?", (list_id,))
        conn.execute("DELETE FROM mining_lists WHERE id = ?", (list_id,))


def load_all() -> list["_ListState"]:
    """水合：按创建时间升序还原全部列表状态（供仓库 __init__ 装回内存）。"""
    conn = db.connect()
    lists = conn.execute("SELECT * FROM mining_lists ORDER BY created_at").fetchall()
    states: list["_ListState"] = []
    for item in lists:
        state = _hydrate_list(dict(item))
        if state is not None:
            states.append(state)
    return states


# ── 内部实现 ──────────────────────────────────────────────────────────────


def _hydrate_list(item: dict) -> "_ListState | None":
    """把 mining_lists 的一行还原成 _ListState。坏数据跳过而不让进程起不来。"""
    from .targets import _ListState, _apply_progress  # 局部导入避免循环依赖

    list_id = item["id"]
    mode = item["mode"]
    conn = db.connect()
    rows_raw = conn.execute(
        "SELECT * FROM mining_rows WHERE list_id = ? ORDER BY rowid", (list_id,)
    ).fetchall()

    try:
        target_list = _rebuild_target_list(item)
        criteria = serialize.loads(item["criteria_json"], list[Criterion])
        columns = [TargetColumn.model_validate(c) for c in json.loads(item["columns_json"])]
        rows: list[RowT] = []
        judgments: dict[str, Judgment] = {}
        records = {}
        for raw in rows_raw:
            row = _rebuild_row(mode, raw)
            if row is None:
                continue
            rows.append(row)
            if raw["judgment_json"] and raw["judgment_json"] != "null":
                judgments[row.id] = serialize.loads(raw["judgment_json"], Judgment)
            record_type = CompanyRecord if mode == "company" else PersonRecord
            if raw["record_json"] and raw["record_json"] != "{}":
                record = serialize.loads(raw["record_json"], record_type)
                key = _record_key(record)
                if key:
                    records[key] = record
    except Exception:  # noqa: BLE001 — 一条坏数据不能阻止进程启动
        return None

    state = _ListState(
        target_list=target_list,
        rows=rows,
        criteria=criteria,
        judgments=judgments,
        records=records,
        columns=columns,
    )
    if item["outreach_json"]:
        state.outreach = OutreachPlan.model_validate_json(item["outreach_json"])
    if target_list.status == "running":
        # 中断的挖掘按完成处理：行早已判定完毕，只剩进度动画没走完（见模块 docstring）。
        state.started_at = time.monotonic()
        target_list.status = "completed"
        _apply_progress(state, stage="completed", verified=len(rows), completed=True)
    return state


def _rebuild_target_list(item: dict) -> TargetList:
    return TargetList(
        id=item["id"],
        query=item["query"],
        mode=item["mode"],
        status=item["status"],
        progress=item["progress"],
        requested_count=item["requested_count"],
        discovered_count=item["discovered_count"],
        contact_count=item["contact_count"],
        condition_items=[
            TargetCondition.model_validate(c) for c in json.loads(item["condition_items_json"])
        ],
        strategy_groups=[
            StrategyGroup.model_validate(s) for s in json.loads(item["strategy_groups_json"])
        ],
        follow_up_plan=item["follow_up_plan_json"],
        created_at=datetime.fromtimestamp(item["created_at"], tz=timezone.utc),
        updated_at=datetime.fromtimestamp(item["updated_at"], tz=timezone.utc),
        phase=item["status"] if item["status"] != "running" else "completed",
        source_id=item["recall_source_id"],
        source_name=item["recall_source_id"],
    )


def _rebuild_row(mode: str, raw: dict) -> RowT | None:
    try:
        if mode == "people":
            return TargetPerson.model_validate_json(raw["row_json"])
        return TargetCompany.model_validate_json(raw["row_json"])
    except Exception:  # noqa: BLE001 — 单行损坏跳过，其余行照常回看
        return None


def _row_key(row: RowT) -> str:
    """行的稳定键——与 targets.py 的 `_row_key` 同口径（复制以避免循环导入）。"""
    return row.website if isinstance(row, TargetCompany) else row.source_url


def _record_key(record) -> str:
    """记录的稳定键——与 targets.py 的 `_record_key` 同口径。"""
    return record.domain if isinstance(record, CompanyRecord) else record.source_url


def _seed_from(value: str) -> int:
    """与 targets.py 的 `_seed_from` 同口径（CRC32，跨进程稳定）。"""
    return zlib.crc32(value.encode()) % 100_000
