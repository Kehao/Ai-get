"""潜客挖掘的内存状态仓库。

不依赖数据库：任务进度由创建时间推算，因此无需后台线程或定时任务。
每个列表持有自己的一份行数据副本，避免不同列表互相影响。
"""

from __future__ import annotations

import csv
import io
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import MINING_DURATION_SECONDS
from ..models import (
    CompanyPage,
    Contact,
    CreateOutreachRequest,
    MatchLevel,
    OutreachPlan,
    OutreachStep,
    SearchMode,
    TargetColumn,
    TargetCompany,
    TargetList,
    TaskStatus,
)
from ..mock.people import build_contacts
from ..mock.company_corpus import CompanySeed
from ..mock.synth import CITIES, COMPANY_INDEX

_UPLOAD_HEADER_HINTS = ("公司", "企业", "名称", "name", "company")

_OUTREACH_TEMPLATE: tuple[tuple[str, str, str, str], ...] = (
    ("第 1 天", "暖场邮件", "基于公司背景和意向信号发送个性化开场", "邮件"),
    ("第 2 天", "LinkedIn：点赞内容", "先互动对方最近内容，让名字自然出现", "LinkedIn"),
    ("第 3 天", "LinkedIn：发送连接请求", "带着上下文发送连接请求", "LinkedIn"),
    ("第 5 天", "WhatsApp 跟进", "基于前面所有上下文继续自然跟进", "WhatsApp"),
    ("第 7 天", "会议已预约", "对方在通话前已经对你建立熟悉感", "会议"),
)

_MATCH_REASONS: dict[str, str] = {
    "明确符合": "命中画像关键词，行业、地区与规模条件一致，可直接进入触达序列。",
    "可能符合": "行业与地区匹配，但规模或融资阶段信息不足，建议人工确认后再跟进。",
    "待确认": "公开信息较少，仅部分条件吻合，需要补充调研后再判断是否跟进。",
}

_MATCH_LEVEL_ORDER: dict[str, int] = {"明确符合": 0, "可能符合": 1, "待确认": 2}


@dataclass
class _ListState:
    target_list: TargetList
    rows: list[TargetCompany]
    columns: list[TargetColumn] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    outreach: OutreachPlan | None = None


class TargetListRepository:
    """潜客列表的读写入口。所有公开方法都在同一把锁下操作，保证并发安全。"""

    def __init__(self) -> None:
        self._states: dict[str, _ListState] = {}
        self._lock = threading.RLock()

    # ── 列表生命周期 ────────────────────────────────────────────────────

    def create_list(self, query: str, mode: SearchMode, count: int) -> TargetList:
        list_id = uuid.uuid4().hex[:12]
        seed = _seed_from(list_id)
        columns = _default_columns(list_id)
        now = datetime.now(timezone.utc)
        target_list = TargetList(
            id=list_id,
            query=query,
            mode=mode,
            status="running",
            progress=0,
            requested_count=count,
            discovered_count=0,
            contact_count=0,
            conditions=_derive_conditions(query),
            follow_up_plan=None,
            created_at=now,
            updated_at=now,
        )
        state = _ListState(
            target_list=target_list,
            rows=_build_rows(seed, count, columns, _detect_city(query)),
            columns=columns,
        )
        with self._lock:
            self._states[list_id] = state
            self._refresh(state)
        return state.target_list

    def create_list_from_upload(self, content: bytes) -> tuple[str, int]:
        names = _parse_uploaded_names(content)
        if not names:
            raise ValueError("未能在文件中识别到公司名称列")

        list_id = uuid.uuid4().hex[:12]
        seed = _seed_from(list_id)
        columns = _default_columns(list_id)
        now = datetime.now(timezone.utc)
        target_list = TargetList(
            id=list_id,
            query=f"上传客户列表：已导入 {len(names)} 家公司",
            mode="company",
            status="completed",
            progress=100,
            requested_count=len(names),
            discovered_count=len(names),
            contact_count=0,
            conditions=["按上传文件中的公司名称逐条富化", "补齐行业、AI 摘要与联系方式"],
            follow_up_plan=None,
            created_at=now,
            updated_at=now,
        )
        rows = _build_rows(seed, len(names), columns, preferred_city=None, names_override=names)
        state = _ListState(target_list=target_list, rows=rows, columns=columns)
        with self._lock:
            self._states[list_id] = state
            self._refresh(state)
        return list_id, len(names)

    def delete_list(self, list_id: str) -> bool:
        with self._lock:
            return self._states.pop(list_id, None) is not None

    # ── 查询 ────────────────────────────────────────────────────────────

    def all_lists(self) -> list[TargetList]:
        with self._lock:
            states = list(self._states.values())
            for state in states:
                self._refresh(state)
            return sorted((state.target_list for state in states), key=lambda item: item.created_at, reverse=True)

    def stats(self) -> tuple[int, int, int]:
        """返回 (结果条数, 进行中任务数, 列表个数)。"""
        lists = self.all_lists()
        company_total = sum(item.discovered_count for item in lists if item.status == "completed")
        running = sum(1 for item in lists if item.status == "running")
        return company_total, running, len(lists)

    def get_list(self, list_id: str) -> TargetList | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            self._refresh(state)
            return state.target_list

    def columns(self, list_id: str) -> list[TargetColumn]:
        with self._lock:
            state = self._states.get(list_id)
            return list(state.columns) if state else []

    def page_companies(
        self,
        list_id: str,
        page: int,
        page_size: int,
        keyword: str = "",
        match_level: str = "",
        sort: str = "match",
    ) -> CompanyPage:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return CompanyPage(items=[], total=0, page=page, page_size=page_size)

            self._refresh(state)
            visible = state.rows[: state.target_list.discovered_count]
            filtered = [row for row in visible if _matches_filters(row, keyword, match_level)]
            ordered = _sort_rows(filtered, sort, state.rows)
            start = (page - 1) * page_size
            return CompanyPage(
                items=ordered[start : start + page_size],
                total=len(ordered),
                page=page,
                page_size=page_size,
            )

    def find_company(self, list_id: str, row_id: str) -> TargetCompany | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            return next((row for row in state.rows if row.id == row_id), None)

    def contacts(self, list_id: str, row_id: str) -> list[Contact]:
        company = self.find_company(list_id, row_id)
        if company is None or company.contact_count == 0:
            return []
        return build_contacts(_seed_from(row_id), company.website, company.contact_count)

    # ── 变更 ────────────────────────────────────────────────────────────

    def add_column(self, list_id: str, name: str) -> TargetColumn | None:
        column = TargetColumn(id=f"column-{uuid.uuid4().hex[:8]}", name=name, created_at=datetime.now(timezone.utc))
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            state.columns.append(column)
            for index, row in enumerate(state.rows):
                row.custom_values[column.id] = _custom_value(name, row, index)
            state.target_list.updated_at = datetime.now(timezone.utc)
            return column

    def add_more(self, list_id: str, count: int) -> TargetList | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None

            extra_seed = _seed_from(list_id) + len(state.rows)
            extra_rows = _build_rows(
                extra_seed,
                count,
                state.columns,
                _detect_city(state.target_list.query),
            )
            state.rows.extend(extra_rows)
            state.target_list.requested_count = len(state.rows)
            state.target_list.discovered_count = len(state.rows)
            state.target_list.status = "completed"
            state.target_list.progress = 100
            state.target_list.updated_at = datetime.now(timezone.utc)
            self._refresh(state)
            return state.target_list

    def retry_field(self, list_id: str, row_id: str, field_name: str) -> TargetCompany | None:
        """重新富化某个字段。字段名与前端列一一对应，未知字段抛出 ValueError。"""
        with self._lock:
            state = self._states.get(list_id)
            company = self.find_company(list_id, row_id)
            if state is None or company is None:
                return None

            index = state.rows.index(company)
            if field_name == "summary":
                company.summary_state = "ready"
                company.ai_summary = _resummarize(company, index)
            elif field_name == "contacts":
                company.contact_state = "ready"
                company.contact_count = 2 + (index % 3)
            elif field_name == "official_contact":
                company.official_contact_state = "ready"
            else:
                raise ValueError(f"不支持的字段：{field_name}")

            state.target_list.contact_count = sum(row.contact_count for row in state.rows)
            state.target_list.updated_at = datetime.now(timezone.utc)
            return company

    def create_outreach(self, list_id: str, request: CreateOutreachRequest) -> OutreachPlan | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None

            steps = [
                OutreachStep(day_label=day, title=title, detail=detail, channel=channel)
                for day, title, detail, channel in _OUTREACH_TEMPLATE
            ]
            plan = OutreachPlan(
                id=f"outreach-{uuid.uuid4().hex[:8]}",
                list_id=list_id,
                agent_name=request.agent_name,
                channel=request.channel,
                status_label="已创建",
                steps=steps,
                created_at=datetime.now(timezone.utc),
            )
            state.outreach = plan
            state.target_list.follow_up_plan = f"智能触达 · {request.channel} · 5 个触点"
            state.target_list.updated_at = datetime.now(timezone.utc)
            return plan

    def outreach(self, list_id: str) -> OutreachPlan | None:
        with self._lock:
            state = self._states.get(list_id)
            return state.outreach if state else None

    # ── 内部 ────────────────────────────────────────────────────────────

    def _refresh(self, state: _ListState) -> None:
        """按已过时间推进进度；完成后不再变化。"""
        if state.target_list.status == "completed":
            return

        elapsed = time.monotonic() - state.started_at
        ratio = min(1.0, elapsed / MINING_DURATION_SECONDS)
        progress = int(ratio * 100)
        total = len(state.rows)
        discovered = total if progress >= 100 else max(0, int(total * ratio))

        state.target_list.progress = progress
        state.target_list.discovered_count = discovered
        state.target_list.contact_count = sum(row.contact_count for row in state.rows[:discovered])
        if progress >= 100:
            state.target_list.status = "completed"
        state.target_list.updated_at = datetime.now(timezone.utc)


def _seed_from(value: str) -> int:
    """用 CRC32 而不是内置 hash，保证结果在进程重启后依然稳定。"""
    return zlib.crc32(value.encode()) % 100_000


def _default_columns(list_id: str) -> list[TargetColumn]:
    """内置列直接用记录字段渲染，因此不参与自定义取值。"""
    now = datetime.now(timezone.utc)
    return [
        TargetColumn(id=f"column-{list_id}-contacts", name="企业关键联系人挖掘", is_builtin=True, created_at=now),
        TargetColumn(id=f"column-{list_id}-official", name="官网联系方式挖掘", is_builtin=True, created_at=now),
    ]


def _build_rows(
    seed: int,
    count: int,
    columns: list[TargetColumn],
    preferred_city: str | None,
    names_override: list[str] | None = None,
) -> list[TargetCompany]:
    rows: list[TargetCompany] = []
    seeds = _select_seeds(seed, count, preferred_city)

    for index, company in enumerate(seeds):
        name = names_override[index] if names_override and index < len(names_override) else company.name
        row_id = f"row-{seed}-{index}"
        summary_state = "failed" if index % 9 == 3 else "ready"
        contact_state = "failed" if index % 6 == 2 else "ready"
        official_contact_state = "blocked" if index % 7 == 5 else "ready"
        contact_count = 0 if contact_state == "failed" else 1 + (index % 4) + (3 if index % 5 == 0 else 0)
        match_level: MatchLevel = "明确符合"
        if index % 11 == 4:
            match_level = "可能符合"
        elif index % 17 == 9:
            match_level = "待确认"

        rows.append(
            TargetCompany(
                id=row_id,
                company_name=name,
                website=company.domain,
                industries=list(company.industries),
                ai_summary=company.summary if summary_state == "ready" else "",
                summary_state=summary_state,
                match_level=match_level,
                match_reason=_MATCH_REASONS[match_level],
                contact_count=contact_count,
                contact_state=contact_state,
                official_contact_state=official_contact_state,
                location=company.location,
                employees=company.employees,
                funding_stage=company.funding_stage,
                custom_values={},
            )
        )

    for column in (item for item in columns if not item.is_builtin):
        for index, row in enumerate(rows):
            row.custom_values[column.id] = _custom_value(column.name, row, index)
    return rows


def _select_seeds(seed: int, count: int, preferred_city: str | None) -> list[CompanySeed]:
    """先取目标城市的条目再取其他，使画像中提到的城市优先出现在结果里。"""
    pool_size = max(count, COMPANY_INDEX.corpus_size)
    seeds = [COMPANY_INDEX.at(index, preferred_city) for index in range(pool_size)]

    if not preferred_city:
        offset = seed % pool_size
        return (seeds[offset:] + seeds[:offset])[:count]

    matching = [item for item in seeds if preferred_city in item.location]
    others = [item for item in seeds if preferred_city not in item.location]
    offset = seed % max(1, len(matching))
    return (matching[offset:] + matching[:offset] + others)[:count]


def _custom_value(column_name: str, row: TargetCompany, index: int) -> str:
    """按列名生成可读的自定义富化结果。"""
    if "小程序" in column_name:
        options = ("已上线小程序", "使用服务商小程序", "暂未发现小程序")
    elif "招聘" in column_name or "岗位" in column_name:
        options = ("近 3 个月有招聘动作", "招聘信息陈旧", "未发现招聘信息")
    elif "技术栈" in column_name or "系统" in column_name:
        options = ("自建系统为主", "采购 SaaS 为主", "混合方案")
    elif "预算" in column_name or "规模" in column_name:
        options = (f"年投入约 {80 + index * 7} 万", f"年投入约 {30 + index * 5} 万", "投入规模不明")
    else:
        options = ("已确认", "待核实", "信息不足")
    return options[index % len(options)]


def _resummarize(company: TargetCompany, index: int) -> str:
    return (
        f"{company.company_name}位于{company.location}，属于{'、'.join(company.industries)}领域，"
        f"员工规模约 {company.employees}，当前融资阶段为 {company.funding_stage}。"
        "重新生成摘要时补充了官网与公开报道信息，可用于判断其业务重心与潜在需求。"
    )


def _matches_filters(row: TargetCompany, keyword: str, match_level: str) -> bool:
    if match_level and row.match_level != match_level:
        return False
    if not keyword:
        return True

    haystack = " ".join([row.company_name, row.website, row.ai_summary, row.location, *row.industries])
    return keyword.lower() in haystack.lower()


def _sort_rows(rows: list[TargetCompany], sort: str, all_rows: list[TargetCompany]) -> list[TargetCompany]:
    """默认排序保留生成时的相关度顺序：先看匹配结论，再看画像条件的命中先后。"""
    if sort == "name":
        return sorted(rows, key=lambda row: row.company_name)
    if sort == "website":
        return sorted(rows, key=lambda row: row.website)

    relevance = {row.id: index for index, row in enumerate(all_rows)}
    return sorted(rows, key=lambda row: (_MATCH_LEVEL_ORDER[row.match_level], relevance[row.id]))


def _derive_conditions(query: str) -> list[str]:
    """把用户输入的画像描述拆成展示用的条件条目，单条保持简短。"""
    conditions = [_shorten(item) for item in _split_query(query) if item.strip()][:4]

    city = _detect_city(query)
    if city:
        conditions.append(f"优先选择在{city}的企业")
    conditions.append("补齐行业、规模与联系方式后再进入触达")
    return conditions


def _detect_city(query: str) -> str | None:
    return next((city for city in CITIES if city in query), None)


def _shorten(text: str, limit: int = 22) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else f"{stripped[:limit]}…"


def _split_query(query: str) -> list[str]:
    normalized = query
    for separator in ("，", ",", "；", ";", "。", "、", "\n"):
        normalized = normalized.replace(separator, "|")
    return normalized.split("|")


def _parse_uploaded_names(content: bytes) -> list[str]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    names: list[str] = []
    for index, row in enumerate(reader):
        if not row:
            continue
        candidate = row[0].strip()
        if not candidate:
            continue
        if index == 0 and any(hint in candidate.lower() for hint in _UPLOAD_HEADER_HINTS):
            continue
        names.append(candidate)
    return names[:1000]
