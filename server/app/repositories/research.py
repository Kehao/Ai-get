"""企业背调记录仓库。进度同样由创建时间推算，不依赖后台任务。"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import RESEARCH_DURATION_SECONDS
from ..models import ResearchDetail, ResearchMessage, ResearchPage, ResearchRecord
from ..mock.reports import build_report, tool_names_for

_TOOL_CALL_COUNT = 4


@dataclass
class _RecordState:
    record: ResearchRecord
    messages: list[ResearchMessage] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)


class ResearchRepository:
    def __init__(self) -> None:
        self._states: dict[str, _RecordState] = {}
        self._lock = threading.RLock()
        self._seed_demo_records()

    def _seed_demo_records(self) -> None:
        for query in (
            "杭州云栖智能科技有限公司的背景与业务概览",
            "帮我查一下成都蜀味调味品有限公司以及最近的状况",
        ):
            self.create(query, completed=True)

    def create(self, query: str, completed: bool = False) -> ResearchRecord:
        record_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        title = _derive_title(query)
        markdown = build_report(query, _seed_from(record_id))

        record = ResearchRecord(
            id=record_id,
            query=query,
            title=title,
            status="completed" if completed else "running",
            progress=100 if completed else 0,
            card_count=_count_report_sections(markdown),
            conversation_turns=1,
            tool_calls=_TOOL_CALL_COUNT,
            report_markdown=markdown,
            created_at=now,
            updated_at=now,
        )
        messages = [
            ResearchMessage(id=f"{record_id}-q", role="user", content=query),
            *(
                ResearchMessage(
                    id=f"{record_id}-t{index}",
                    role="assistant",
                    content=f"调用工具：{name}",
                    tool_name=name,
                )
                for index, name in enumerate(tool_names_for(query))
            ),
            ResearchMessage(id=f"{record_id}-a", role="assistant", content=markdown),
        ]

        state = _RecordState(record=record, messages=messages)
        if completed:
            state.started_at = time.monotonic() - RESEARCH_DURATION_SECONDS

        with self._lock:
            self._states[record_id] = state
            return self._refreshed(state)

    def summary(self) -> ResearchPage:
        with self._lock:
            records = [self._refreshed(state) for state in self._states.values()]
        ordered = sorted(records, key=lambda item: item.created_at, reverse=True)
        return ResearchPage(
            report_count=sum(1 for item in ordered if item.status == "completed"),
            running_count=sum(1 for item in ordered if item.status == "running"),
            records=ordered,
        )

    def detail(self, record_id: str) -> ResearchDetail | None:
        with self._lock:
            state = self._states.get(record_id)
            if state is None:
                return None
            return ResearchDetail(record=self._refreshed(state), messages=list(state.messages))

    def delete(self, record_id: str) -> bool:
        with self._lock:
            return self._states.pop(record_id, None) is not None

    def _refreshed(self, state: _RecordState) -> ResearchRecord:
        if state.record.status == "completed":
            return state.record

        elapsed = time.monotonic() - state.started_at
        ratio = min(1.0, elapsed / RESEARCH_DURATION_SECONDS)
        state.record.progress = int(ratio * 100)
        if ratio >= 1.0:
            state.record.status = "completed"
            state.record.progress = 100
        state.record.updated_at = datetime.now(timezone.utc)
        return state.record


def _seed_from(value: str) -> int:
    return sum(ord(char) for char in value)


def _count_report_sections(markdown: str) -> int:
    """报告中的二级标题数量，对应页面上的「数据卡片」数。"""
    return sum(1 for line in markdown.splitlines() if line.startswith("## "))


_LEADING_PREFIXES: tuple[str, ...] = (
    "帮我查一下",
    "帮我查",
    "帮我对",
    "帮我调研",
    "帮我",
    "把我查一下",
    "把我查",
    "把我",
    "查询",
    "分析",
    "调研",
    "了解一下",
    "查一下",
    "关于",
    "对",
)

_TRAILING_PHRASES: tuple[str, ...] = (
    "这家公司以及最近的状况",
    "以及最近的状况",
    "这家公司",
    "的背景与业务概览",
    "公开背景概览",
    "进行贸易背调",
    "进行企业背调",
    "进行背调",
    "进行调研",
)

_ELLIPSIS = "，。？！?！ "


def _derive_title(query: str) -> str:
    """从查询句中提炼报告标题：去掉口语化前缀与任务后缀，保留主体名称。"""
    cleaned = query.strip()
    for prefix in _LEADING_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break

    for phrase in _TRAILING_PHRASES:
        cleaned = cleaned.replace(phrase, "")

    cleaned = cleaned.strip(_ELLIPSIS)
    for tail in ("股份有限公司", "有限公司"):
        if cleaned.endswith(tail):
            cleaned = cleaned[: -len(tail)]
            break
    return cleaned[:20] or query[:20]
