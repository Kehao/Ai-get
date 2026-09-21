"""潜客挖掘的内存状态仓库。

## 职责边界

这个模块**只管状态机与分页**：谁在跑、跑到哪一阶段、结果怎么筛怎么排。
它自己不生成任何候选数据——

- **候选**来自数据源层 `providers`（按能力查找，可整体替换）；
- **标准与结论**来自资格层 `qualification`（L0 生成标准、L3 逐条判定）。

这条边界是「可扩展性」的全部意义所在：以后接入真实爬虫只需要新增一个 provider，
这里一行都不用改。

## 进度为什么不是随机数

任务进度由创建时间推算，所以普通挖掘不需要后台线程；但推进的是**真实阶段**
（`generating_criteria → searching → verifying → completed`），
四元组计数（goal / verified / qualified / full）来自已落库的判定结果，
因此恒满足 `full ≤ qualified ≤ verified ≤ goal`——进度条不会和数字打架。

唯一的例外是智能发现：提炼按批（每批 5 家）在后台线程里跑，每落一批
`discovered_count` 才前移一格——它的进度是**真实的逐批推进**，不是推算。
"""

from __future__ import annotations

import csv
import io
import logging
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import cast

from ..agents.company_discovery.adapters import (
    deepen_project_entity,
    extract_project_entities,
    search_project_documents,
)
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
    Evidence,
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

logger = logging.getLogger(__name__)
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

# 深挖与发现的规模上限现在都在 agent 配置里（`server/agent-configs/*.json`），
# 由 `app/agents/adapters.py` 读取。这里刻意不再留常量——那会变成第二个真源。

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

    def create_list_from_agent(self, profile: str, count: int = 0) -> TargetList:
        """创建「智能发现」列表：先落一张 running 的空表**立即返回**，后台逐批补行。

        `count` 是前端「结果数量」选择框的值（0＝不指定，走 agent 配置默认），
        由 `_agent_search_plan` 折算成检索条数与提炼轮数。

        提炼按批走（每批最多 5 家）：每落一批行，`discovered_count` 就前移一格——
        分页只展示 `rows[:discovered_count]`，详情页现有的 2.5 秒轮询会自然把
        新一批行显示出来，不需要额外的推送通道。

        **评判与打分与 `create_list` 完全同源**：同样的 L0 标准生成、同样的
        L3 规则判定（纯规则、零额外成本）、同样的准入条件评估——提炼阶段
        模型顺带读出的 summary / 行业 / 融资阶段正是判定的输入。

        后台线程的每次状态改动都拿 `self._lock`，与前台读写互斥；线程是 daemon，
        进程退出时未跑完的批次直接丢弃——水合层会把 running 列表按 completed
        收尾，已落库的行不丢。
        """
        build = _build_criteria("company", profile)
        criteria = list(build.criteria)

        list_id = uuid.uuid4().hex[:12]
        columns = _default_columns(list_id, "company")
        now = datetime.now(timezone.utc)

        target_list = TargetList(
            id=list_id,
            query=f"智能发现：{profile}",
            mode="company",
            status="running",
            progress=0,
            requested_count=0,
            discovered_count=0,
            contact_count=0,
            condition_items=_conditions_from_criteria(criteria),
            # 策略组与条件同源（都来自画像）：不生成的话详情页的「挖掘策略」卡永不显示
            strategy_groups=build_strategy_groups(profile, "company"),
            follow_up_plan=None,
            created_at=now,
            updated_at=now,
            phase="searching",
            source_id="agent-discovery",
            source_name="智能发现 agent",
        )
        _stamp_criteria_source(target_list, build)
        state = _ListState(
            target_list=target_list,
            rows=[],
            criteria=criteria,
            columns=columns,
        )
        with self._lock:
            self._states[list_id] = state
            list_store.save(state)

        threading.Thread(
            target=self._run_agent_discovery,
            args=(state, profile, count),
            daemon=True,
            name=f"agent-discovery-{list_id}",
        ).start()
        return state.target_list

    def _run_agent_discovery(self, state: _ListState, profile: str, count: int = 0) -> None:
        """智能发现的后台执行体：检索 → 分批提炼 → 每批落行并写穿。"""
        top_k, max_documents, max_rounds = _agent_search_plan(count)
        # 计划总数提前暴露（轮数 × 每批 5）：前端据此给「还没到的批次」铺骨架——
        # 第一批落 5 行，下面就垫 15 行灰条，逐批消减；跑完回填真实行数。
        expected = (max_rounds or 3) * 5
        with self._lock:
            state.target_list.requested_count = expected
            list_store.save(state)
        try:
            documents = search_project_documents(profile, top_k=top_k)
            extract_project_entities(
                profile,
                documents,
                on_batch=lambda batch: self._append_agent_batch(state, batch, documents),
                max_documents=max_documents,
                max_rounds=max_rounds,
            )
        except Exception:  # noqa: BLE001 — 后台线程不能把异常带崩进程；失败按完成收尾
            logger.warning("智能发现后台执行失败：%s", state.target_list.id, exc_info=True)
        finally:
            with self._lock:
                _apply_progress(state, stage="completed", verified=len(state.rows), completed=True)
                state.target_list.requested_count = len(state.rows)
                detail = state.target_list.progress_detail
                if detail is not None:
                    # 通用收尾话术是「已达到目标数量」——智能发现的目标只是折算规模，
                    # 实际行数由材料决定，照实说。
                    detail.stop_reason = (
                        f"共发现 {len(state.rows)} 家候选（按选择规模折算检索与提炼轮数，实际以材料为准）"
                        if state.rows
                        else "这批网页里没有提炼出符合条件的候选，可换个画像描述再试"
                    )
                list_store.save(state)

    def _append_agent_batch(self, state: _ListState, batch: tuple[dict, ...], documents: tuple[dict, ...]) -> None:
        """把一批提炼实体落成行（判定与普通挖掘同源），落完立即写穿。"""
        with self._lock:
            now = datetime.now(timezone.utc)
            for offset, entity in enumerate(batch):
                index = len(state.rows)
                record, row = _candidate_to_row(
                    entity,
                    documents=documents,
                    row_id=f"row-{_seed_from(state.target_list.id)}-{index}",
                    created_at=now,
                )
                judgment = _judge_record("company", list(state.criteria), record)
                # 规则判定为准（与普通挖掘同口径）：模型初判保留在 dossier_reason 里互相印证。
                row.match_level = _match_level(judgment.match_level)
                row.match_reason = judgment.reason
                row.score = judgment.score
                state.rows.append(row)
                state.records[_record_key(record)] = record
                state.judgments[row.id] = judgment
            state.target_list.discovered_count = len(state.rows)
            state.target_list.progress = min(85, 4 * len(state.rows))
            state.target_list.updated_at = now
            list_store.save(state)

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

        if field_name == "official_contact":
            # 官网联系方式的唯一真实来源是深挖（抓官网 + 模型整理）。旧实现什么都不
            # 抓就把状态置 ready，搞出一批「已获取但空空如也」的行——改为真走深挖。
            return self.deep_dive_company(list_id, row_id)

        with self._lock:
            target.summary_state = "ready"
            target.ai_summary = _resummarize(target, index)
            state.target_list.updated_at = datetime.now(timezone.utc)
            list_store.save(state)
            return target

    def deep_dive_company(self, list_id: str, row_id: str) -> TargetCompany | None:
        """对一行企业做深挖：抓页面 → 定位官网 → 用 LLM 把档案补齐。**仅会社模式支持。**

        与 `retry_field` 的分工：那个是「向数据源再要一次同一个字段」，
        这个是「换一套手段把整份档案补齐」——所以它一次改多个字段，
        并把结论写进 `dossier_*` 三个字段，让前端能说清「挖过了、还缺什么」。

        深挖要跑 LLM 和外部抓取，单次十几秒，因此**必须在锁外调用**：
        占着 `self._lock` 会让同一列表的分页、详情、保存一起卡住。
        """
        with self._lock:
            state = self._states.get(list_id)
            if state is None:
                return None
            if state.is_people:
                raise ValueError("找人模式暂不支持深挖：深挖面向企业档案")
            row = next((item for item in state.rows if item.id == row_id), None)
            if row is None:
                return None

            target = cast(TargetCompany, row)
            record = _record_of(state, row)
            documents = _documents_from_evidence(record)
            domain = target.website or (
                record.domain if isinstance(record, CompanyRecord) else ""
            )
            profile = state.target_list.query
            name = target.company_name

        try:
            dossier = deepen_project_entity(profile, name, documents, domain=domain)
        except Exception as error:  # noqa: BLE001 — 深挖失败不该让接口报 500
            # 把原因写进状态再返回：前端能显示「深挖失败：…」，
            # 用户也知道该去查配置，而不是反复点。
            #
            # 这里捕的是宽泛的 Exception：`deepen_entity` 对检索、抓取、整理都已静默降级，
            # 能冒到这里的只可能是配置损坏或适配器故障——那些同样该被展示成状态，
            # 而不是变成一屏堆栈。
            with self._lock:
                target.dossier_state = "failed"
                target.dossier_reason = f"深挖失败：{error}"
                state.target_list.updated_at = datetime.now(timezone.utc)
                list_store.save(state)
                return target

        with self._lock:
            website_before = target.website
            written, extra = _apply_dossier(target, record, dossier)
            # 行的稳定键就是 website，补上域名会让键漂移——必须一并搬一次 records 的索引，
            # 否则详情页的 References 与富化台账会突然查不到这家公司的原始记录。
            enriched = record
            if isinstance(record, CompanyRecord) and (
                target.website != website_before or written or extra
            ):
                # 重判要吃**记录本体**字段（location/employees/funding_stage/…），
                # _apply_dossier 只写了行——这里把深挖补全同步回记录，判定才见得到。
                moved = replace(
                    record,
                    domain=target.website,
                    name=target.company_name or record.name,
                    industries=tuple(target.industries) or record.industries,
                    summary=target.ai_summary or record.summary,
                    location=target.location or record.location,
                    employees=target.employees or record.employees,
                    funding_stage=target.funding_stage or record.funding_stage,
                    attributes={**record.attributes, **extra, **written},
                )
                state.records.pop(_record_key(record), None)
                state.records[_record_key(moved)] = moved
                enriched = moved
            # 无行落点的字段进 agent_fields：前端「挖掘档案」区块逐键展示。
            if extra:
                target.agent_fields = {**(target.agent_fields or {}), **extra}

            # 深挖后重判（综合结果流程）：档案补齐了判定要吃的字段（地区/规模/融资
            # 阶段/行业…），带着补全后的记录再过一次 L3 规则判定——综合结果与
            # 匹配分随之刷新。模型初判留在 dossier_reason，规则结论在 match_reason，
            # 两个口径都能看到、互不覆盖。
            if isinstance(enriched, CompanyRecord) and state.criteria:
                judgment = _judge_record("company", list(state.criteria), enriched)
                target.match_level = _match_level(judgment.match_level)
                target.match_reason = judgment.reason
                target.score = judgment.score

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

    ⚠️ 主字段为空时必须**退化到名称**，不能留空串：百度召回的第二阶段
    （爱企查站点限定）返回的候选天生没有域名，多条空键会在索引里互相覆盖，
    回查时张冠李戴。`baidu_source._company_key` 早就是这个口径，这里跟上。
    """
    if isinstance(record, CompanyRecord):
        return record.domain.strip() or record.name.strip()
    return record.source_url.strip() or record.name.strip()


def _index_records(records: list[CompanyRecord] | list[PersonRecord]) -> dict[str, CompanyRecord | PersonRecord]:
    """按稳定键建索引，用于回查原始记录（判定与证据都要回到它）。"""
    return {_record_key(record): record for record in records}


def _row_key(row: RowT) -> str:
    """行的稳定键，与 `_record_key` **逐字对应**——包括空值退化的口径。

    两个键任何一处对不齐，「行 → 原始记录」的回查都会静默落空：
    详情页的 References 与富化台账会凭空消失，而不会报错。
    """
    if isinstance(row, TargetCompany):
        return row.website.strip() or row.company_name.strip()
    return row.source_url.strip() or row.name.strip()


def _row_title(row: RowT) -> str:
    """行在「名称」列上的显示文本：公司名或人名。"""
    return row.company_name if isinstance(row, TargetCompany) else row.name


def _row_contact_total(rows: list[RowT]) -> int:
    """两套行对「可触达」的口径不同，各自算各自的。"""
    return sum(row.contact_count for row in rows)


def _record_of(state: _ListState, row: RowT) -> CompanyRecord | PersonRecord | None:
    """按行的稳定键回查数据源记录。判定与证据都要回到原始记录，而不是从展示字段倒推。"""
    return state.records.get(_row_key(row))


def _candidate_to_row(
    entity: dict,
    documents: Sequence[Mapping[str, Any]],
    *,
    row_id: str,
    created_at: datetime,
) -> tuple[CompanyRecord, TargetCompany]:
    """把提炼出的候选折成「记录 + 行」——**轻档案**，还没深挖。

    与该实体相关的原始网页存进行 `evidence`：详情页点「深挖」时，
    `_documents_from_evidence` 取它们当材料，两段流程就此衔接。

    提炼阶段模型已顺带读出 `summary` / `industries` / `location` / `funding_stage`
    这些轻字段——它们是规则判定的输入，让智能发现的打分与普通挖掘同口径。
    """
    name = str(entity.get("name", "")).strip() or "未命名实体"
    domain = str(entity.get("domain", "")).strip()
    matched = bool(entity.get("matched"))
    reason = str(entity.get("reason", "")).strip()
    evidence_url = str(entity.get("evidence_url", ""))

    # 字段表里没有行落点的（legal_name / products / …）全部进 attributes：
    # 数据不丢，详情页台账要展示哪个再扩白名单。
    _row_fields = {
        "name", "domain", "matched", "reason", "evidence_url",
        "industries", "summary", "location", "funding_stage",
    }
    extra = {
        key: ("、".join(value) if isinstance(value, (list, tuple)) else str(value))
        for key, value in entity.items()
        if key not in _row_fields and value
    }
    summary = str(entity.get("summary", "")).strip()
    industries = tuple(str(item).strip() for item in entity.get("industries") or [])
    location = str(entity.get("location", "")).strip()
    funding_stage = str(entity.get("funding_stage", "")).strip()

    related = [
        page
        for page in documents
        if name and name in f"{page.get('title', '')} {page.get('content', '')}"
    ]
    evidence = tuple(
        Evidence(
            title=str(page.get("title", ""))[:120],
            url=str(page.get("url", "")),
            snippet=str(page.get("content", ""))[:200],
        )
        for page in related[:4]
    ) or ((Evidence(title=name, url=evidence_url, snippet=reason),) if evidence_url else ())

    record = CompanyRecord(
        external_id=f"agent-{row_id}",
        name=name,
        domain=domain,
        industries=industries,
        summary=summary,
        location=location,
        funding_stage=funding_stage,
        contact_count=0,
        evidence=evidence,
        missing_fields=frozenset({"contacts", "official_contact"}),
        source_id="agent-discovery",
        attributes={"agent": "discovery-agent", "agent_reason": reason, **extra},
    )
    row = TargetCompany(
        id=row_id,
        company_name=name,
        website=domain,
        industries=list(industries),
        ai_summary=summary,
        summary_state="ready" if summary else "failed",
        match_level="明确符合" if matched else "可能符合",
        match_reason=reason,
        contact_count=0,
        contact_state="failed",
        official_contact_state="blocked",
        location=location,
        employees="",
        funding_stage=funding_stage,
        created_at=created_at,
        custom_values={},
        score=90 if matched else 45,
        dossier_state="blocked",
        dossier_reason=reason,
        dossier_missing=[],
        # 无行落点的字段（工商/产品/融资明细…）进 agent_fields，前端详情页展示。
        agent_fields=dict(extra),
    )
    return record, row


def _documents_from_evidence(record: RecordT | None) -> tuple[dict, ...]:
    """把召回记录的证据折成深挖要的「检索结果」形状。

    列表状态里只落了 `CompanyRecord`（原始检索结果没进库），但它带着 evidence：
    `snippet` 是召回时截下的正文片段，够用来定位这家公司；L1 会按 url 重新抓全文，
    所以这里不需要完整正文。
    """
    if not isinstance(record, CompanyRecord):
        return ()
    return tuple(
        {"title": item.title, "url": item.url, "content": item.snippet}
        for item in record.evidence
        if item.url
    )


def _apply_dossier(
    company: TargetCompany,
    record: CompanyRecord | None,
    dossier: dict,
) -> tuple[dict[str, str], dict[str, str]]:
    """把深挖结果填进行。**只填空字段**——深挖是补全，不是覆写。

    与 `merge_enrichment` 同一口径：召回已经给出的值更接近源头，
    深挖来的值可能出自一篇二手报道，不该反过来盖掉它。

    返回**本轮新写入的键值**，供调用方并回 `record.attributes`——字段表里
    没有行落点的字段（legal_name / products / …）也保住数据，不再白挖。
    """
    company.dossier_state = "ready"
    company.dossier_reason = str(dossier.get("reason", ""))
    company.dossier_missing = [str(item) for item in dossier.get("missing") or []]

    written: dict[str, str] = {}

    # 名字升级：深挖整理出的名字往往比提炼阶段的简名更完整（典型如
    # 「领健Linkedcare」→「江苏领健智能科技有限公司」）。工商注册名最权威，
    # 有它优先用它；否则认深挖档案的名字（整理时已做过规范升级）。相同则不动。
    upgraded = str(dossier.get("legal_name", "")).strip() or str(dossier.get("name", "")).strip()
    if upgraded and upgraded != company.company_name:
        company.company_name = upgraded
        written["name"] = upgraded

    if not company.website:
        company.website = str(dossier.get("domain", ""))
        if company.website:
            written["domain"] = company.website
    if not company.ai_summary and dossier.get("summary"):
        company.ai_summary = str(dossier["summary"])
        company.summary_state = "ready"
        written["summary"] = company.ai_summary
    if not company.industries:
        company.industries = [str(item) for item in dossier.get("industries") or []]
        if company.industries:
            written["industries"] = "、".join(company.industries)
    for field_name in ("location", "employees", "funding_stage"):
        if not getattr(company, field_name) and dossier.get(field_name):
            setattr(company, field_name, str(dossier[field_name]))
            written[field_name] = str(dossier[field_name])
    # logo 由抓取层直取（非 LLM 产出），有就用——但同样只填空，不覆写。
    if not company.logo_url and dossier.get("logo"):
        company.logo_url = str(dossier["logo"])
        written["logo"] = company.logo_url

    # 深挖带出官网联系方式时，把调研状态一并置为就绪——表格「官网联系方式挖掘」
    # 列与详情「智能调研」区读的都是这个状态；只写 agent_fields 不回写状态，
    # 就会出现「档案里有邮箱、调研区却显示未找到」的矛盾（实测踩过）。
    if str(dossier.get("official_contact", "")).strip():
        company.official_contact_state = "ready"

    # 无行落点的字段（legal_name / products / registered_capital / …）：
    # 不丢，整批进 extra——调用方并进 record.attributes 与 row.agent_fields。
    _with_row_field = {
        "name", "domain", "summary", "industries", "location",
        "employees", "funding_stage", "matched", "reason", "missing",
        "evidence_url", "logo",
    }
    extra: dict[str, str] = {}
    for key, value in dossier.items():
        if key in _with_row_field or not value:
            continue
        extra[key] = "、".join(value) if isinstance(value, (list, tuple)) else str(value)
    return written, extra


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


def _agent_search_plan(count: int) -> tuple[int, int, int]:
    """把前端「结果数量」折算成智能发现的规模：`(top_k, max_documents, max_rounds)`。

    百度 v2 单次检索硬上限 20 条（v1 是 10），所以 25 以上的档位**靠多轮提炼**
    把同一批网页里的实体榨干净，而不是硬堆检索量——候选数受材料上限约束，
    轮次模型榨干会提前停，最终行数如实回填 `requested_count`。
    返回 0 值表示「走 agent 配置默认」。
    """
    if count <= 0:
        return 0, 0, 0
    top_k = max(10, min(count, 20))
    max_rounds = max(2, min(6, -(-count // 5)))
    return top_k, top_k, max_rounds


def _refresh(state: _ListState) -> None:
    """按已用时间推进任务阶段；完成后不再变化。

    智能发现列表**不参与**这套时间推算：它的行在后台线程里逐批真实落库，
    `discovered_count` / `progress` 由线程推进——这里再按 elapsed 覆写一遍，
    会把已落库的行重新藏回「未发现」（实测 5 行秒变 0 行）。
    """
    if state.target_list.status == "completed":
        return
    if state.target_list.source_id == "agent-discovery":
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
