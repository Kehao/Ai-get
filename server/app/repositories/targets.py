"""潜客挖掘的内存状态仓库。

## 职责边界

这个模块**只管状态机与分页**：谁在跑、跑到哪一阶段、结果怎么筛怎么排。
它自己不生成任何候选数据——

- **候选**来自数据源层 `providers`（按能力查找，可整体替换）；
- **标准与结论**来自资格层 `qualification`（L0 生成标准、L3 逐条判定）。

这条边界是「可扩展性」的全部意义所在：以后接入真实爬虫只需要新增一个 provider，
这里一行都不用改。

## 进度为什么不是随机数

任务进度由创建时间推算，所以不需要后台线程；但推进的是**真实阶段**
（`generating_criteria → searching → verifying → completed`），
四元组计数（goal / verified / qualified / full）来自已落库的判定结果，
因此恒满足 `full ≤ qualified ≤ verified ≤ goal`——进度条不会和数字打架。
"""

from __future__ import annotations

import csv
import io
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import cast

from ..config import MINING_DURATION_SECONDS, MINING_PHASE_WEIGHTS
from ..models import (
    CompanyPage,
    Contact,
    CreateOutreachRequest,
    EnrichmentLedger,
    MatchLevel,
    MiningPhase,
    MiningProgress,
    OutreachPlan,
    OutreachStep,
    PersonPage,
    SearchMode,
    TargetColumn,
    TargetCompany,
    TargetCompanyDetail,
    TargetCondition,
    TargetList,
    TargetPerson,
    TargetPersonDetail,
)
from ..providers import (
    CompanyQuery,
    CompanyRecord,
    ContactQuery,
    PersonQuery,
    PersonRecord,
    SourceError,
    call_source,
    company_source,
    contact_source,
    enrich_companies,
    manifests,
    person_source,
)
from ..qualification import (
    MATCH_FULL,
    MATCH_UNCONFIRMED,
    CriteriaBuild,
    Criterion,
    Judgment,
    build_criteria_detailed,
    build_person_criteria_detailed,
    company_hints,
    judge,
    judge_person,
    person_hints,
)
from ..mock.dossiers import (
    build_evaluations,
    build_outreach_note,
    build_person_outreach_note,
    build_person_references,
    build_person_research_results,
    build_references,
    build_research_results,
)
from ..mock.strategy import CONDITION_COLORS, build_strategy_groups
from . import list_store

_UPLOAD_HEADER_HINTS = ("公司", "企业", "名称", "name", "company")

_UPLOAD_QUERY = "按上传文件中的公司名称逐条富化，补齐行业、AI 摘要与联系方式"

_OUTREACH_TEMPLATE: tuple[tuple[str, str, str, str], ...] = (
    ("第 1 天", "暖场邮件", "基于公司背景和意向信号发送个性化开场", "邮件"),
    ("第 2 天", "LinkedIn：点赞内容", "先互动对方最近内容，让名字自然出现", "LinkedIn"),
    ("第 3 天", "LinkedIn：发送连接请求", "带着上下文发送连接请求", "LinkedIn"),
    ("第 5 天", "WhatsApp 跟进", "基于前面所有上下文继续自然跟进", "WhatsApp"),
    ("第 7 天", "会议已预约", "对方在通话前已经对你建立熟悉感", "会议"),
)

_MATCH_LEVEL_ORDER: dict[str, int] = {"明确符合": 0, "可能符合": 1, "待确认": 2}

# 一个列表里的行要么全是企业、要么全是人物，两种模式的行**不混存**。
# 行与记录的类型跟着 `target_list.mode` 走，判据只有一处：`_ListState.is_people`。
RowT = TargetCompany | TargetPerson
RecordT = CompanyRecord | PersonRecord


@dataclass
class _ListState:
    target_list: TargetList
    rows: list[RowT]
    criteria: list[Criterion] = field(default_factory=list)
    judgments: dict[str, Judgment] = field(default_factory=dict)
    records: dict[str, RecordT] = field(default_factory=dict)
    columns: list[TargetColumn] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    outreach: OutreachPlan | None = None

    @property
    def is_people(self) -> bool:
        return self.target_list.mode == "people"


class TargetListRepository:
    """潜客列表的读写入口。所有公开方法都在同一把锁下操作，保证并发安全。"""

    def __init__(self) -> None:
        self._states: dict[str, _ListState] = {}
        self._lock = threading.RLock()
        # P7 水合：重启后把历史列表从 SQLite 装回内存，调用方零感知。
        for state in list_store.load_all():
            self._states[state.target_list.id] = state

    # ── 列表生命周期 ────────────────────────────────────────────────────

    def create_list(self, query: str, mode: SearchMode, count: int) -> TargetList:
        list_id = uuid.uuid4().hex[:12]
        seed = _seed_from(list_id)
        columns = _default_columns(list_id, mode)
        build = _build_criteria(mode, query)
        criteria = list(build.criteria)
        now = datetime.now(timezone.utc)

        records, source_id = _recall(mode=mode, query=query, limit=count, seed=seed, criteria=criteria)
        rows, judgments = _build_rows(mode, records, criteria, columns, seed, created_at=now)

        target_list = TargetList(
            id=list_id,
            query=query,
            mode=mode,
            status="running",
            progress=0,
            requested_count=count,
            discovered_count=0,
            contact_count=0,
            condition_items=_conditions_from_criteria(criteria),
            strategy_groups=build_strategy_groups(query, mode),
            follow_up_plan=None,
            created_at=now,
            updated_at=now,
            phase="generating_criteria",
            source_id=source_id,
            source_name=_source_name(source_id),
        )
        _stamp_criteria_source(target_list, build)
        state = _ListState(
            target_list=target_list,
            rows=rows,
            criteria=criteria,
            judgments=judgments,
            records=_index_records(records),
            columns=columns,
        )
        with self._lock:
            self._states[list_id] = state
            _apply_progress(state, stage="generating_criteria", verified=0, completed=False)
            list_store.save(state)
        return state.target_list

    def create_list_from_upload(self, content: bytes) -> tuple[str, int]:
        names = _parse_uploaded_names(content)
        if not names:
            raise ValueError("未能在文件中识别到公司名称列")

        list_id = uuid.uuid4().hex[:12]
        seed = _seed_from(list_id)
        columns = _default_columns(list_id, "company")
        build = _build_criteria("company", _UPLOAD_QUERY)
        criteria = list(build.criteria)
        now = datetime.now(timezone.utc)

        records, source_id = _recall(
            mode="company", query=_UPLOAD_QUERY, limit=len(names), seed=seed, criteria=criteria, names=tuple(names)
        )
        rows, judgments = _build_rows("company", records, criteria, columns, seed, created_at=now)

        target_list = TargetList(
            id=list_id,
            query=f"上传客户列表：已导入 {len(names)} 家公司",
            mode="company",
            status="completed",
            progress=100,
            requested_count=len(names),
            discovered_count=len(names),
            contact_count=sum(row.contact_count for row in rows),
            condition_items=_conditions_from_criteria(criteria),
            strategy_groups=[],
            follow_up_plan=None,
            created_at=now,
            updated_at=now,
            phase="completed",
            source_id=source_id,
            source_name=_source_name(source_id),
        )
        _stamp_criteria_source(target_list, build)
        state = _ListState(
            target_list=target_list,
            rows=rows,
            criteria=criteria,
            judgments=judgments,
            records=_index_records(records),
            columns=columns,
        )
        with self._lock:
            self._states[list_id] = state
            _apply_progress(state, stage="completed", verified=len(rows), completed=True)
            list_store.save(state)
        return list_id, len(names)

    def delete_list(self, list_id: str) -> bool:
        with self._lock:
            existed = self._states.pop(list_id, None) is not None
        if existed:
            list_store.delete(list_id)
        return existed

    # ── 查询 ────────────────────────────────────────────────────────────

    def all_lists(self) -> list[TargetList]:
        with self._lock:
            states = list(self._states.values())
            for state in states:
                _refresh(state)
            return sorted((state.target_list for state in states), key=lambda item: item.created_at, reverse=True)

    def stats(self) -> tuple[int, int, int]:
        """返回 (结果行数, 进行中任务数, 列表个数)。

        结果行数把公司行与人物行**一起算**：概览说的是「挖到了多少条记录」，
        不区分模式，否则人物列表的结果会在概览里凭空消失。
        """
        lists = self.all_lists()
        row_total = sum(item.discovered_count for item in lists if item.status == "completed")
        running = sum(1 for item in lists if item.status == "running")
        return row_total, running, len(lists)

    def get_list(self, list_id: str) -> TargetList | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            _refresh(state)
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
            if state is None or state.is_people:
                return CompanyPage(items=[], total=0, page=page, page_size=page_size)

            _refresh(state)
            visible = state.rows[: state.target_list.discovered_count]
            filtered = [row for row in visible if _matches_filters(row, keyword, match_level)]
            ordered = _sort_rows(filtered, sort, state.rows)
            start = (page - 1) * page_size
            return CompanyPage(
                items=cast(list[TargetCompany], ordered[start : start + page_size]),
                total=len(ordered),
                page=page,
                page_size=page_size,
            )

    def page_people(
        self,
        list_id: str,
        page: int,
        page_size: int,
        keyword: str = "",
        match_level: str = "",
        sort: str = "match",
    ) -> PersonPage:
        """人物列表的一页。

        与会社侧共用筛选与排序的实现（`_matches_filters` / `_sort_rows` 只认
        `_row_title` 与 `_search_text` 两个访问器），但**分页结果各自成型**——
        人物行没有行业、规模、融资字段，包装成 `CompanyPage` 就只能是空值堆积。
        """
        with self._lock:
            state = self._states.get(list_id)
            if state is None or not state.is_people:
                return PersonPage(items=[], total=0, page=page, page_size=page_size)

            _refresh(state)
            visible = state.rows[: state.target_list.discovered_count]
            filtered = [row for row in visible if _matches_filters(row, keyword, match_level)]
            ordered = _sort_rows(filtered, sort, state.rows)
            start = (page - 1) * page_size
            return PersonPage(
                items=cast(list[TargetPerson], ordered[start : start + page_size]),
                total=len(ordered),
                page=page,
                page_size=page_size,
            )

    def find_company(self, list_id: str, row_id: str) -> TargetCompany | None:
        with self._lock:
            state = self._states.get(list_id)
            if state is None or state.is_people:
                return None
            return next((cast(TargetCompany, row) for row in state.rows if row.id == row_id), None)

    def contacts(self, list_id: str, row_id: str) -> list[Contact]:
        """按**已验证域名**向数据源取联系人，而不是用公司名去猜域名。仅会社模式。"""
        with self._lock:
            state = self._states.get(list_id)
            if state is None or state.is_people:
                return []
            company = next((row for row in state.rows if row.id == row_id), None)
            if company is None:
                return []
            target = cast(TargetCompany, company)
            if target.contact_count == 0:
                return []
            domain = target.website
            limit = target.contact_count
            seed = _seed_from(row_id)

        result = call_source(
            contact_source(),
            "contact_search",
            ContactQuery(domain=domain, limit=limit, seed=seed),
        )
        return [
            Contact(
                id=item.external_id,
                name=item.name,
                title=item.title,
                email=item.email,
                linkedin=item.linkedin,
                phone=item.phone,
                confidence=item.confidence,
            )
            for item in result.items
        ]

    def company_detail(self, list_id: str, row_id: str) -> TargetCompanyDetail | None:
        """企业详情页所需的完整内容：档案、参考资料、触达说明、调研结果与准入条件评估。"""
        with self._lock:
            state = self._states.get(list_id)
            if state is None or state.is_people:
                return None
            company = next((row for row in state.rows if row.id == row_id), None)
            if company is None:
                return None

            return TargetCompanyDetail(
                company=cast(TargetCompany, company),
                references=build_references(cast(TargetCompany, company), _record_of(state, company)),
                outreach_note=build_outreach_note(cast(TargetCompany, company), state.outreach is not None),
                outreach=state.outreach,
                research_results=build_research_results(cast(TargetCompany, company)),
                evaluations=build_evaluations(state.judgments.get(company.id)),
                enrichment=_enrichment_ledger(_record_of(state, company)),
            )

    def person_detail(self, list_id: str, row_id: str) -> TargetPersonDetail | None:
        """人物详情面板所需的完整内容。

        区块骨架与会社详情一致（档案 / References / 智能调研 / 智能触达 / 准入条件评估），
        因为用户是在同一个面板里读它；不同的是准入条件评估来自**人物标准的判定结果**，
        以及调研项换成人物侧的那两项。
        """
        with self._lock:
            state = self._states.get(list_id)
            if state is None or not state.is_people:
                return None
            person = next((row for row in state.rows if row.id == row_id), None)
            if person is None:
                return None

            target = cast(TargetPerson, person)
            return TargetPersonDetail(
                person=target,
                references=build_person_references(target, _record_of(state, person)),
                outreach_note=build_person_outreach_note(target, state.outreach is not None),
                outreach=state.outreach,
                research_results=build_person_research_results(target),
                evaluations=build_evaluations(state.judgments.get(target.id)),
            )

    # ── 变更 ────────────────────────────────────────────────────────────

    def add_column(self, list_id: str, name: str) -> TargetColumn | None:
        column = TargetColumn(id=f"column-{uuid.uuid4().hex[:8]}", name=name, created_at=datetime.now(timezone.utc))
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            state.columns.append(column)
            for index, row in enumerate(state.rows):
                row.custom_values[column.id] = _custom_value(name, index)
            state.target_list.updated_at = datetime.now(timezone.utc)
            list_store.save(state)
            return column

    def add_more(self, list_id: str, count: int) -> TargetList | None:
        """追加一批结果。沿用同一份标准，只换召回种子，因此结论口径与首批一致。"""
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            mode = state.target_list.mode
            taken = {_row_key(row) for row in state.rows}
            criteria = state.criteria
            query = state.target_list.query
            extra_seed = _seed_from(list_id) + len(state.rows)

        records, _source_id = _recall(
            mode=mode,
            query=query,
            limit=count,
            seed=extra_seed,
            criteria=criteria,
            exclude_keys=taken,
        )

        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None

            new_rows, new_judgments = _build_rows(
                mode,
                records,
                criteria,
                state.columns,
                extra_seed,
                offset=len(state.rows),
            )
            state.rows.extend(new_rows)
            state.judgments.update(new_judgments)
            for record in records:
                state.records[_record_key(record)] = record

            state.target_list.requested_count = len(state.rows)
            state.target_list.status = "completed"
            state.target_list.phase = "completed"
            state.target_list.progress = 100
            state.target_list.updated_at = datetime.now(timezone.utc)
            _apply_progress(state, stage="completed", verified=len(state.rows), completed=True)
            list_store.save(state)
            return state.target_list

    def update_conditions(
        self,
        list_id: str,
        query: str | None,
        conditions: list[str],
    ) -> TargetList | None:
        """保存挖掘配置。

        标准会就地重建并**重新判定已召回的企业**——因为准入条件评估是标准的产物，
        标准改了却留着旧评估，详情页就会和列表页的结论自相矛盾。
        重新判定不会换一批企业，换企业要显式调用 `remine`。
        """
        cleaned = [item.strip() for item in conditions if item.strip()]
        if not cleaned:
            raise ValueError("至少需要保留一条判断条件")

        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None

            if query is not None and query.strip():
                state.target_list.query = query.strip()

            build = _build_criteria(state.target_list.mode, state.target_list.query, cleaned)
            criteria = list(build.criteria)
            _rejudge(state, criteria)
            state.target_list.condition_items = _conditions_from_criteria(criteria)
            state.target_list.strategy_groups = build_strategy_groups(
                state.target_list.query, state.target_list.mode
            )
            state.target_list.updated_at = datetime.now(timezone.utc)
            _stamp_criteria_source(state.target_list, build)
            _apply_progress(
                state,
                stage=state.target_list.phase,
                verified=state.target_list.discovered_count,
                completed=state.target_list.status == "completed",
            )
            list_store.save(state)
            return state.target_list

    def remine(self, list_id: str) -> TargetList | None:
        """按最新配置重跑挖掘：重建标准、换一批结果、进度归零。"""
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            mode = state.target_list.mode
            query = state.target_list.query
            count = state.target_list.requested_count or len(state.rows)
            columns = state.columns
            # 重建标准必须带上已保存的条件文本——只按 query 重建会把用户配置的条件
            # 全部丢掉，「改完条件点挖掘」得到的结果就像没改过一样。
            # 文本里有引擎自产的条件名：合并侧的回传守卫会跳过，用户条件则幂等重建。
            saved_conditions = [item.text for item in state.target_list.condition_items]
            seed = _seed_from(f"{list_id}-{int(time.time() * 1000)}")
            now = datetime.now(timezone.utc)

        build = _build_criteria(mode, query, saved_conditions)
        criteria = list(build.criteria)
        records, source_id = _recall(mode=mode, query=query, limit=count, seed=seed, criteria=criteria)
        rows, judgments = _build_rows(mode, records, criteria, columns, seed, created_at=now)

        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            state.rows = rows
            state.criteria = criteria
            state.judgments = judgments
            state.records = _index_records(records)
            state.started_at = time.monotonic()
            state.target_list.condition_items = _conditions_from_criteria(criteria)
            state.target_list.source_id = source_id
            state.target_list.source_name = _source_name(source_id)
            _stamp_criteria_source(state.target_list, build)
            state.target_list.status = "running"
            state.target_list.progress = 0
            state.target_list.discovered_count = 0
            state.target_list.contact_count = 0
            state.target_list.updated_at = now
            _apply_progress(state, stage="generating_criteria", verified=0, completed=False)
            list_store.save(state)
            return state.target_list

    def retry_field(self, list_id: str, row_id: str, field_name: str) -> TargetCompany | None:
        """重新富化某个字段。**仅会社模式支持。**

        联系人是真的再向数据源要一次（这正是接上真实爬虫后该有的行为）；
        摘要与官网联系方式目前仍是本地重新生成，因为演示源没有对应的重试接口。

        人物模式明确拒绝而不是假装成功：会社侧之所以能重试，是因为
        `contact_search` 是一个独立能力（输入域名、输出联系人），可以单独再调一次；
        人物源目前只有「按画像找人」这一个能力，没有「按人补字段」的接口，
        本地凭空造一个值只会让前端以为这条链路是通的。
        """
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            if state.is_people:
                raise ValueError("找人模式暂不支持字段重试：数据源没有「按人补字段」的能力")
            company = next((row for row in state.rows if row.id == row_id), None)
            if company is None:
                return None

            index = state.rows.index(company)
            if field_name == "contacts":
                domain = company.website
                seed = _seed_from(row_id)
            elif field_name in ("summary", "official_contact"):
                domain = ""
                seed = _seed_from(row_id)
            else:
                raise ValueError(f"不支持的字段：{field_name}")

            target = cast(TargetCompany, company)

        if field_name == "contacts":
            result = call_source(
                contact_source(),
                "contact_search",
                ContactQuery(domain=domain, limit=4, seed=seed),
            )
            with self._lock:
                target.contact_state = "ready"
                target.contact_count = len(result.items)
                state.target_list.contact_count = _row_contact_total(state.rows)
                state.target_list.updated_at = datetime.now(timezone.utc)
                list_store.save(state)
            return target

        with self._lock:
            if field_name == "summary":
                target.summary_state = "ready"
                target.ai_summary = _resummarize(target, index)
            else:
                target.official_contact_state = "ready"
            state.target_list.updated_at = datetime.now(timezone.utc)
            list_store.save(state)
            return target

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
            list_store.save(state)
            return plan

    def outreach(self, list_id: str) -> OutreachPlan | None:
        with self._lock:
            state = self._states.get(list_id)
            return state.outreach if state else None


# ── 召回与判定 ────────────────────────────────────────────────────────────


def _build_criteria(mode: SearchMode, query: str, user_conditions: list[str] | None = None) -> CriteriaBuild:
    """按模式选标准引擎。

    两个引擎**并列而不是同一个**：找公司判的是地域与行业，找人判的是姓名与职位，
    维度不重叠（见 `qualification` 的模块说明）。这里是整个仓库里唯一决定
    「用哪套标准」的地方——新增入口时记得也走这里，别直接调某个引擎。
    """
    if mode == "people":
        return build_person_criteria_detailed(query, user_conditions=user_conditions or ())
    return build_criteria_detailed(query, user_conditions=user_conditions or ())


def _recall(
    mode: SearchMode,
    *,
    query: str,
    limit: int,
    seed: int,
    criteria: list[Criterion] | None = None,
    names: tuple[str, ...] = (),
    exclude_keys: set[str] | None = None,
) -> tuple[list[CompanyRecord] | list[PersonRecord], str]:
    """向数据源要一批候选。

    召回提示**从已冻结的标准里派生**，而不是重新解析一遍画像：
    标准是这条任务的真源（用户可能刚改过条件），重解析会得到第三条互相矛盾的理解。

    这里不做任何「补数量」的动作：数据源给多少就是多少，
    凑数是召回层的事，不该由状态机悄悄替它完成。
    """
    blocked = exclude_keys or set()

    if mode == "people":
        hints = person_hints(criteria or [])
        people_result = call_source(
            person_source(),
            "person_search",
            PersonQuery(
                text=query,
                limit=limit + len(blocked),
                preferred_city=hints.city,
                name_hints=hints.name_hints,
                role_hints=hints.role_hints,
                company_hints=hints.company_hints,
                seed=seed,
            ),
        )
        people: list[PersonRecord] = [
            record for record in people_result.items if _record_key(record) not in blocked
        ]
        return people[:limit], people_result.source_id

    company = company_hints(criteria or [])
    company_result = call_source(
        company_source(),
        "company_search",
        CompanyQuery(
            text=query,
            limit=limit + len(blocked),
            mode="company",
            preferred_city=company.city,
            industry_hints=company.industry_hints,
            names=names,
            seed=seed,
        ),
    )
    companies: list[CompanyRecord] = [
        record for record in company_result.items if _record_key(record) not in blocked
    ]
    # P5 字段补齐：召回给「是谁」，补齐源给「还有什么字段」。没有注册补齐源
    # （PDL key 未配置）时它原样返回，不会多一次调用；补齐失败也不影响召回结果。
    companies = enrich_companies(companies)
    return companies[:limit], company_result.source_id


def _build_rows(
    mode: SearchMode,
    records: list[CompanyRecord] | list[PersonRecord],
    criteria: list[Criterion],
    columns: list[TargetColumn],
    seed: int,
    *,
    offset: int = 0,
    created_at: datetime | None = None,
) -> tuple[list[RowT], dict[str, Judgment]]:
    """把数据源记录翻译成列表行，并逐条执行 L3 判定。

    行的 `match_level` / `match_reason` / `score` **全部来自判定结果**，
    不再是写死的三档文案——这是「为什么这条匹配」能被复核的前提。

    两种模式的行**形状不同**（公司有行业/规模/融资/联系人数，人物有职位/所属公司/档案地址），
    所以分行构建，只共用行 id、判定与创建时间的生成规则。
    """
    rows: list[RowT] = []
    judgments: dict[str, Judgment] = {}
    stamp = created_at or datetime.now(timezone.utc)
    builder = _build_person_row if mode == "people" else _build_company_row

    for index, record in enumerate(records):
        row_id = f"row-{seed}-{offset + index}"
        judgment = _judge_record(mode, criteria, record)
        judgments[row_id] = judgment
        rows.append(
            builder(
                record=record,
                row_id=row_id,
                judgment=judgment,
                created_at=stamp + timedelta(seconds=index * 7),
            )
        )

    for column in (item for item in columns if not item.is_builtin):
        for index, row in enumerate(rows):
            row.custom_values[column.id] = _custom_value(column.name, index)
    return rows, judgments


def _build_company_row(
    *,
    record: CompanyRecord | PersonRecord,
    row_id: str,
    judgment: Judgment,
    created_at: datetime,
) -> TargetCompany:
    company = cast(CompanyRecord, record)
    return TargetCompany(
        id=row_id,
        company_name=company.name,
        website=company.domain,
        industries=list(company.industries),
        ai_summary=company.summary,
        summary_state="failed" if "summary" in company.missing_fields else "ready",
        match_level=_match_level(judgment.match_level),
        match_reason=judgment.reason,
        contact_count=company.contact_count,
        contact_state="failed" if "contacts" in company.missing_fields else "ready",
        official_contact_state="blocked" if "official_contact" in company.missing_fields else "ready",
        location=company.location,
        employees=company.employees,
        funding_stage=company.funding_stage,
        created_at=created_at,
        custom_values={},
        score=judgment.score,
    )


def _build_person_row(
    *,
    record: CompanyRecord | PersonRecord,
    row_id: str,
    judgment: Judgment,
    created_at: datetime,
) -> TargetPerson:
    person = cast(PersonRecord, record)
    has_contact = bool(person.contact_email or person.contact_phone)
    return TargetPerson(
        id=row_id,
        name=person.name,
        name_local=person.name_local,
        title=person.title,
        company=person.company,
        company_domain=person.company_domain,
        source_label=person.source_label,
        source_url=person.source_url,
        ai_summary=person.summary,
        summary_state="failed" if "summary" in person.missing_fields else "ready",
        match_level=_match_level(judgment.match_level),
        match_reason=judgment.reason,
        location=person.location,
        contact_count=1 if has_contact else 0,
        contact_state="ready" if has_contact else "failed",
        created_at=created_at,
        custom_values={},
        score=judgment.score,
    )


def _judge_record(
    mode: SearchMode,
    criteria: list[Criterion],
    record: CompanyRecord | PersonRecord,
) -> Judgment:
    if mode == "people":
        return judge_person(criteria, cast(PersonRecord, record))
    return judge(criteria, cast(CompanyRecord, record))


def _rejudge(state: _ListState, criteria: list[Criterion]) -> None:
    """标准变化后重新判定已召回的记录，保证结论与标准始终同源。"""
    mode = state.target_list.mode
    state.criteria = criteria
    state.judgments = {}
    for row in state.rows:
        record = _record_of(state, row)
        if record is None:
            continue
        judgment = _judge_record(mode, criteria, record)
        state.judgments[row.id] = judgment
        row.match_level = _match_level(judgment.match_level)
        row.match_reason = judgment.reason
        row.score = judgment.score


def _record_key(record: CompanyRecord | PersonRecord) -> str:
    """记录在状态里的索引键。

    会社用域名、人物用档案地址——两者都是**行上直接可读**的字段，
    这样「行 → 原始记录」的回查不需要额外维护一份映射。
    人物刻意不用 `PersonRecord.dedupe_key`：它在档案地址缺失时会退化成 `姓名@公司`，
    而行上没有这个值，回查会静默落空。
    """
    return record.domain if isinstance(record, CompanyRecord) else record.source_url


def _index_records(records: list[CompanyRecord] | list[PersonRecord]) -> dict[str, CompanyRecord | PersonRecord]:
    """按稳定键建索引，用于回查原始记录（判定与证据都要回到它）。"""
    return {_record_key(record): record for record in records}


def _row_key(row: RowT) -> str:
    """行的稳定键，与 `_record_key` 一一对应。"""
    return row.website if isinstance(row, TargetCompany) else row.source_url


def _row_title(row: RowT) -> str:
    """行在「名称」列上的显示文本：公司名或人名。"""
    return row.company_name if isinstance(row, TargetCompany) else row.name


def _row_contact_total(rows: list[RowT]) -> int:
    """两套行对「可触达」的口径不同，各自算各自的。"""
    return sum(row.contact_count for row in rows)


def _record_of(state: _ListState, row: RowT) -> CompanyRecord | PersonRecord | None:
    """按行的稳定键回查数据源记录。判定与证据都要回到原始记录，而不是从展示字段倒推。"""
    return state.records.get(_row_key(row))


# 富化台账展示的字段白名单：attributes 里还有 tavily_score 等内部键，不上屏。
_ENRICHMENT_FIELD_KEYS = ("registered_capital", "legal_rep", "founded", "matched_title", "pdl_id")

_ENRICHMENT_SOURCE_LABELS = {
    "baidu": "百度 AI 搜索（爱企查）",
    "tavily": "Tavily 网页检索",
    "pdl": "People Data Labs",
}


def _enrichment_ledger(record: CompanyRecord | PersonRecord | None) -> EnrichmentLedger:
    """把召回记录的富化痕迹整理成详情页可读的台账；没有富化过就是空台账。"""
    if record is None or not isinstance(record, CompanyRecord):
        return EnrichmentLedger()
    attributes = record.attributes
    enriched_by = attributes.get("enriched_by", "")
    if not enriched_by:
        return EnrichmentLedger()
    fields = {key: attributes[key] for key in _ENRICHMENT_FIELD_KEYS if attributes.get(key)}
    return EnrichmentLedger(
        source_id=enriched_by,
        source_label=_ENRICHMENT_SOURCE_LABELS.get(enriched_by, enriched_by),
        fields=fields,
    )


def _conditions_from_criteria(criteria: list[Criterion]) -> list[TargetCondition]:
    """把标准转成可编辑的条件条目，色条按位置循环分配。"""
    return [
        TargetCondition(
            id=item.id,
            text=item.name,
            color=CONDITION_COLORS[index % len(CONDITION_COLORS)],
            weight=item.weight,
            category=item.category,
            question=item.question,
        )
        for index, item in enumerate(criteria)
    ]


def _stamp_criteria_source(target_list: TargetList, build: CriteriaBuild) -> None:
    """把标准的产出路径冻结进任务记录。

    每一次重建标准（新建、上传导入、改配置、重跑）都要重新盖章：
    上一次可能是 LLM 生成的，这一次可能已经降级到规则引擎，留着旧标签
    会让详情页把「规则引擎的结论」解释成「LLM 的判断」。
    """
    target_list.criteria_source = build.source
    target_list.criteria_label = build.label
    target_list.criteria_fallback_reason = build.fallback_reason


def _match_level(value: str) -> MatchLevel:
    return "明确符合" if value == MATCH_FULL else ("可能符合" if value != MATCH_UNCONFIRMED else "待确认")


def _source_name(source_id: str) -> str:
    return next((item.name for item in manifests() if item.id == source_id), source_id)


# ── 进度状态机 ────────────────────────────────────────────────────────────


def _refresh(state: _ListState) -> None:
    """按已用时间推进任务阶段；完成后不再变化。"""
    if state.target_list.status == "completed":
        return

    elapsed = time.monotonic() - state.started_at
    ratio = min(1.0, elapsed / MINING_DURATION_SECONDS)
    criteria_end = MINING_PHASE_WEIGHTS["generating_criteria"]
    searching_end = criteria_end + MINING_PHASE_WEIGHTS["searching"]
    goal = len(state.rows)

    if ratio < criteria_end:
        _apply_progress(state, stage="generating_criteria", verified=0, completed=False)
        return
    if ratio < searching_end:
        # 召回阶段：候选已拿到但还没判定完，因此验证数仍为 0。
        # 这也意味着列表此刻是空的——真实链路里验证本来就是最慢的一段，
        # 与其先塞一批未判定的候选进去，不如让「已验证」的口径保持干净。
        _apply_progress(state, stage="searching", verified=0, completed=False)
        return

    span = max(1e-6, 1.0 - searching_end)
    progress_in_verify = (ratio - searching_end) / span
    completed = ratio >= 1.0
    verified = goal if completed else int(goal * progress_in_verify)
    _apply_progress(state, stage="completed" if completed else "verifying", verified=verified, completed=completed)


def _apply_progress(state: _ListState, *, stage: MiningPhase, verified: int, completed: bool) -> None:
    """写入阶段与四元组计数。计数的唯一来源是已落库的判定结果。"""
    goal = len(state.rows)
    verified = max(0, min(verified, goal))
    verified_rows = state.rows[:verified]

    qualified = sum(1 for row in verified_rows if row.match_level != "待确认")
    full = sum(1 for row in verified_rows if row.match_level == "明确符合")

    state.target_list.phase = stage
    state.target_list.progress = 100 if completed else min(99, int(100 * _elapsed_ratio(state)))
    state.target_list.discovered_count = verified
    state.target_list.contact_count = _row_contact_total(verified_rows)
    state.target_list.progress_detail = MiningProgress(
        stage=stage,
        goal=goal,
        verified=verified,
        qualified=qualified,
        full=full,
        stop_reason=("已达到目标数量" if verified >= goal else "候选已耗尽") if completed else None,
    )
    if completed:
        state.target_list.status = "completed"
    state.target_list.updated_at = datetime.now(timezone.utc)


def _elapsed_ratio(state: _ListState) -> float:
    return min(1.0, (time.monotonic() - state.started_at) / MINING_DURATION_SECONDS)


# ── 工具函数 ──────────────────────────────────────────────────────────────


def _seed_from(value: str) -> int:
    """用 CRC32 而不是内置 hash，保证结果在进程重启后依然稳定。"""
    return zlib.crc32(value.encode()) % 100_000


def _default_columns(list_id: str, mode: SearchMode) -> list[TargetColumn]:
    """内置列直接用记录字段渲染，因此不参与自定义取值。

    人选模式**没有内置列**：参考站的人物表就是「名称 / 所属公司 / 职位 / 网址 / AI 摘要 / 综合结果」，
    没有「联系人挖掘」这类会社侧字段——人的联系方式走详情面板的智能调研，不占列。
    """
    if mode == "people":
        return []
    now = datetime.now(timezone.utc)
    return [
        TargetColumn(id=f"column-{list_id}-contacts", name="企业关键联系人挖掘", is_builtin=True, created_at=now),
        TargetColumn(id=f"column-{list_id}-official", name="官网联系方式挖掘", is_builtin=True, created_at=now),
    ]


def _custom_value(column_name: str, index: int) -> str:
    """按列名生成可读的自定义富化结果。

    只依赖列名与行号，**不读行上的字段**：自定义列的取值是演示用的确定性文案，
    让它去读行字段会把它和两种模式的行结构绑在一起，而它本来对两者都无所谓。
    """
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


def _search_text(row: RowT) -> str:
    """关键词筛选的检索范围。

    两种模式的可检索字段不同：公司看名称/域名/行业/所在地，人物看姓名（中英）/职位/所属公司/档案地址。
    这里给出各自的合理范围，而不是取两者的字段名并集——并集会让「按行业词搜人」
    命中一堆无关人物，因为人物行上根本没有行业字段。
    """
    if isinstance(row, TargetCompany):
        return " ".join([row.company_name, row.website, row.ai_summary, row.location, *row.industries])
    return " ".join(
        [row.name, row.name_local, row.title, row.company, row.company_domain, row.source_url, row.ai_summary, row.location]
    )


def _matches_filters(row: RowT, keyword: str, match_level: str) -> bool:
    if match_level and row.match_level != match_level:
        return False
    if not keyword:
        return True
    return keyword.lower() in _search_text(row).lower()


def _sort_rows(rows: list[RowT], sort: str, all_rows: list[RowT]) -> list[RowT]:
    """默认排序以判定得分为主，同分时保留召回顺序。

    得分是判定器的直接产物，比「三档结论」更细，因此先按得分排能自然把
    「明确符合里最贴合的那几条」顶到前面。
    """
    if sort == "name":
        return sorted(rows, key=_row_title)
    if sort == "website":
        return sorted(rows, key=_row_key)

    relevance = {row.id: index for index, row in enumerate(all_rows)}
    return sorted(rows, key=lambda row: (_MATCH_LEVEL_ORDER.get(row.match_level, 9), -row.score, relevance[row.id]))


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
