"""领域模型与请求体定义。全部对外返回的数据都经过这里的模型序列化。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import COMPANY_COUNT_OPTIONS, OUTREACH_CHANNELS

MatchLevel = Literal["明确符合", "可能符合", "待确认"]
FieldState = Literal["ready", "failed", "blocked"]
TaskStatus = Literal["pending", "running", "completed", "failed"]
SearchMode = Literal["company", "people"]
ChannelState = Literal["available", "connected", "coming_soon"]
ConditionStatus = Literal["符合", "不确定", "不符合"]
# 智能调研的子任务标识。会社与人物各用各的：会社是「企业关键联系人 / 官网联系方式」，
# 人物是「联系方式 / 档案完整度」——两者不是同一件事，共用标识会让前端
# 不得不用标题去猜该渲染哪种区块。
ResearchKey = Literal["contacts", "official_contact", "person_contact", "profile_completeness"]

# 挖掘任务阶段，与上游 Websets 的状态机保持一致。
MiningPhase = Literal["generating_criteria", "searching", "verifying", "completed"]

# 准入标准的产出路径：LLM 生成，或内置规则引擎兜底。
CriteriaSource = Literal["llm", "rule"]


class User(BaseModel):
    id: str
    email: str
    display_name: str


class CredentialsRequest(BaseModel):
    """登录与注册共用的邮箱密码请求体。"""

    email: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def email_must_contain_at(cls, value: str) -> str:
        if "@" not in value.strip():
            raise ValueError("邮箱格式不正确")
        return value.strip().lower()


class LoginResponse(BaseModel):
    token: str
    user: User


class StatusMessage(BaseModel):
    message: str


class UploadResult(BaseModel):
    list_id: str
    imported_rows: int


# ── 潜客挖掘 ──────────────────────────────────────────────────────────────


class Strategy(BaseModel):
    id: str
    text: str


class CountOption(BaseModel):
    value: int


class TargetCondition(BaseModel):
    """一条挖掘判断条件。

    `color` 是展示用的左侧色条，由后端下发保证前后端一致；
    其余字段来自 L0 资格标准引擎，`weight` 与 `category` 让前端能解释
    「这条条件有多重要、属于哪个维度」，`question` 是它的判定口径。
    """

    id: str
    text: str
    color: str
    weight: int = 0
    category: str = ""
    question: str = ""


class MiningProgress(BaseModel):
    """挖掘进度四元组，字段含义与上游 Websets 的 progress 一致。

    它是**真实计数**而不是插值出来的百分比：`verified` 是已判定过的候选数，
    `qualified` 是通过资格验证的数量，`full` 是完全匹配的数量。
    恒有 `full ≤ qualified ≤ verified ≤ goal`。
    """

    stage: MiningPhase
    goal: int
    verified: int
    qualified: int
    full: int
    stop_reason: str | None = None


class SourceInfo(BaseModel):
    """数据源的自描述，用于让前端说明「这批结果是谁给的」。"""

    id: str
    name: str
    description: str
    capabilities: list[str]
    regions: list[str]
    priority: int
    cost_per_call: float
    requires_credentials: bool


class StrategyGroup(BaseModel):
    """挖掘策略分组：给用户解释「这批结果是怎么被圈出来的」。"""

    id: str
    title: str
    description: str
    examples: list[str]


class TargetList(BaseModel):
    id: str
    query: str
    mode: SearchMode
    status: TaskStatus
    progress: int
    requested_count: int
    discovered_count: int
    contact_count: int
    condition_items: list[TargetCondition]
    strategy_groups: list[StrategyGroup]
    follow_up_plan: str | None
    created_at: datetime
    updated_at: datetime
    phase: MiningPhase = "completed"
    progress_detail: MiningProgress | None = None
    source_id: str = ""
    source_name: str = ""
    # 这批标准由哪条路径产出。标准会被冻结进任务记录，判定结果全由它推导，
    # 所以必须标出产出方——否则 LLM 失败静默降级到规则引擎时，
    # 用户只会看到「标准变了」却不知道原因。
    criteria_source: CriteriaSource = "rule"
    # 产出方的可读标签，直接给前端展示（如 "LLM · criteria/v1 · deepseek-flash"）。
    criteria_label: str = ""
    # 降级发生时记录原因，未降级时为空字符串。
    criteria_fallback_reason: str = ""


class TargetCompany(BaseModel):
    id: str
    company_name: str
    website: str
    industries: list[str]
    ai_summary: str
    summary_state: FieldState
    match_level: MatchLevel
    match_reason: str
    contact_count: int
    contact_state: FieldState
    official_contact_state: FieldState
    location: str
    employees: str
    funding_stage: str
    created_at: datetime
    custom_values: dict[str, str] = Field(default_factory=dict)
    score: int = 0
    # 深挖（爬虫 + LLM 补全档案）的状态与结论。默认 `blocked`＝还没挖过：
    # 要和「字段为空」区分开——空是「没挖」还是「挖过但没有」，前端得说得清。
    dossier_state: FieldState = "blocked"
    dossier_reason: str = ""
    dossier_missing: list[str] = Field(default_factory=list)
    # 智能发现挖出的、没有专属行字段的档案（工商照面 / 产品 / 融资明细…），
    # 键＝字段表里的名字。带默认值，旧记录从 SQLite 水合时自动兼容。
    agent_fields: dict[str, str] = Field(default_factory=dict)
    # 企业 logo 图地址。深挖时由抓取层直取官网图标（非 LLM 产出），空＝没挖过或没抓到。
    logo_url: str = ""


class TargetPerson(BaseModel):
    """找人模式下的一行**人物档案**。

    刻意不复用 `TargetCompany`：两者的列完全不同（人物行是
    名称/所属公司/职位/网址/AI 摘要/综合结果），硬塞进公司模型就会出现
    「行业」列显示职位、「规模」列显示公司名这种错位。
    公司行有行业、规模、融资与联系人计数，人物行有职位、所属公司与档案地址——
    共有的只有判定结论（`match_level` / `match_reason` / `score`）与创建时间。
    """

    id: str
    # 展示名（海外职业档案多为拼音或英文写法）与中文本名，两个都给前端，
    # 由前端决定何时并列显示——判定用的姓名匹配是在后端完成的，这里只是展示。
    name: str
    name_local: str
    title: str
    company: str
    company_domain: str
    # 档案来源（「领英」「公司团队页」…）与档案地址。列表的「网址」列显示成
    # 「来源 + 域名 + 路径」，所以两者都要给。
    source_label: str
    source_url: str
    ai_summary: str
    summary_state: FieldState
    match_level: MatchLevel
    match_reason: str
    location: str
    # 可获取的公开联系方式条数（0 或 1）。人物没有「企业关键联系人」这一层下钻，
    # 所以它不与 `TargetCompany.contact_count` 同义。
    contact_count: int = 0
    contact_state: FieldState = "ready"
    created_at: datetime
    custom_values: dict[str, str] = Field(default_factory=dict)
    score: int = 0


class ReferenceItem(BaseModel):
    title: str
    url: str


class ResearchResult(BaseModel):
    """智能调研的一个子任务结果，对应详情页「智能调研」区块的一行。"""

    key: ResearchKey
    title: str
    state: FieldState
    summary: str
    evidence: list[str]


class ConditionEvaluation(BaseModel):
    """准入条件评估：某条标准在该企业上的判定结果与依据。

    `weight` 与 `condition` 一起复现了这一行的来源标准，使「为什么匹配」可逐条复核。
    `references` 是这条结论的**全部可回溯来源**（参考站评估卡下方的一排来源 chip）；
    为空时前端退回展示 `source_label` / `source_url` 这条单链接。
    """

    condition: str
    status: ConditionStatus
    reference_count: int
    explanation: str
    source_label: str
    source_url: str
    weight: int = 0
    references: list[ReferenceItem] = Field(default_factory=list)


class TargetColumn(BaseModel):
    id: str
    name: str
    is_builtin: bool = False
    created_at: datetime


class Contact(BaseModel):
    id: str
    name: str
    title: str
    email: str
    linkedin: str
    phone: str
    confidence: int


class TargetOverview(BaseModel):
    """潜客挖掘概览。

    `row_count` 是**已完成列表的结果行总数**，公司行与人物行都算，所以不叫 `company_count`。
    """

    row_count: int
    running_count: int
    list_count: int
    lists: list[TargetList]


class CompanyPage(BaseModel):
    items: list[TargetCompany]
    total: int
    page: int
    page_size: int


class PersonPage(BaseModel):
    items: list[TargetPerson]
    total: int
    page: int
    page_size: int


class CreateListRequest(BaseModel):
    query: str = Field(min_length=4, max_length=2000)
    mode: SearchMode = "company"
    count: int = 25


class AddColumnRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)


class AddMoreRequest(BaseModel):
    count: int = 25


class ListDetail(BaseModel):
    """列表详情页的首屏数据。

    `companies` 与 `people` **只填其中一个**，取决于 `target_list.mode`。
    不用「同一个字段装两种行」的写法：那样前端的列定义就只能取两者的交集，
    等于把「找人」硬做成「找公司」的一个皮肤。
    """

    target_list: TargetList
    columns: list[TargetColumn]
    companies: CompanyPage | None = None
    people: PersonPage | None = None


class OutreachStep(BaseModel):
    day_label: str
    title: str
    detail: str
    channel: str


class OutreachPlan(BaseModel):
    id: str
    list_id: str
    agent_name: str
    channel: str
    status_label: str
    steps: list[OutreachStep]
    created_at: datetime


class EnrichmentLedger(BaseModel):
    """富化台账：哪个源补了什么字段。

    照面字段（注册资本/法定代表人/成立日期）来自网页摘要抽取，
    `matched_title` 记录命中的页面标题供人工核对——**不冒充权威数据**。
    """

    source_id: str = ""
    source_label: str = ""
    fields: dict[str, str] = Field(default_factory=dict)


class TargetCompanyDetail(BaseModel):
    company: TargetCompany
    references: list[ReferenceItem]
    outreach_note: str
    outreach: OutreachPlan | None
    research_results: list[ResearchResult]
    evaluations: list[ConditionEvaluation]
    enrichment: EnrichmentLedger = Field(default_factory=EnrichmentLedger)


class TargetPersonDetail(BaseModel):
    """人物详情面板：与会社模式的详情**结构相同、内容不同**。

    区块骨架（档案 / References / 智能调研 / 智能触达 / 准入条件评估）是同一套，
    因为用户要在同一个面板里读它；不同的是档案字段与调研项——
    人物没有「官网联系方式挖掘」这种下钻，只有他自己的档案与联系方式。
    """

    person: TargetPerson
    references: list[ReferenceItem]
    outreach_note: str
    outreach: OutreachPlan | None
    research_results: list[ResearchResult]
    evaluations: list[ConditionEvaluation]


class CreateOutreachRequest(BaseModel):
    agent_name: str = Field(default="Ai-get 默认销售智能体", max_length=60)
    channel: str = Field(default="邮件", max_length=20)


class AgentDiscoverRequest(BaseModel):
    """「智能发现」的入参：一句画像 + 期望结果数量。

    `count` 来自前端「结果数量」选择框（0＝不指定，走 agent 配置默认）。
    它折算成第一步的检索条数与提炼轮数——不是硬性承诺，最终以实际行数为准。
    """

    profile: str = Field(min_length=2, max_length=500)
    count: int = Field(default=0, ge=0)


class UpdateConditionsRequest(BaseModel):
    """保存挖掘配置：寻找对象正文与该正文解析出的条件条目一起提交。"""

    query: str | None = Field(default=None, max_length=2000)
    conditions: list[str] = Field(default_factory=list)


# ── 企业背调 ──────────────────────────────────────────────────────────────


class ResearchRecord(BaseModel):
    id: str
    query: str
    title: str
    status: TaskStatus
    progress: int
    card_count: int
    conversation_turns: int
    tool_calls: int
    report_markdown: str
    created_at: datetime
    updated_at: datetime


class CreateResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class ResearchMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    tool_name: str | None = None


class ResearchDetail(BaseModel):
    record: ResearchRecord
    messages: list[ResearchMessage]


class ResearchPage(BaseModel):
    report_count: int
    running_count: int
    records: list[ResearchRecord]


# ── 智能体 ────────────────────────────────────────────────────────────────


class AgentTemplate(BaseModel):
    id: str
    emoji: str
    name: str
    badge: str
    status_label: str
    description: str
    mode_label: str
    channels: list[str]
    source_label: str


class Agent(BaseModel):
    id: str
    name: str
    emoji: str
    description: str
    status_label: str
    channels: list[str]
    created_at: datetime


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=500)
    emoji: str = Field(default="🤖", max_length=8)
    channels: list[str] = Field(default_factory=list)
    template_id: str | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    status_label: str | None = None


# ── 关联账号 ──────────────────────────────────────────────────────────────


class Channel(BaseModel):
    id: str
    name: str
    group: str
    description: str
    icon: str
    state: ChannelState
    account_label: str | None


class ChannelGroup(BaseModel):
    group: str
    channels: list[Channel]


class ConnectSummary(BaseModel):
    connected_email: int
    total_email: int
    connected_social: int
    total_social: int


class ConnectPage(BaseModel):
    summary: ConnectSummary
    groups: list[ChannelGroup]


# ── 知识库 ────────────────────────────────────────────────────────────────


class KnowledgeEntry(BaseModel):
    id: str
    question: str
    answer: str


class KnowledgeBase(BaseModel):
    id: str
    name: str
    source_url: str
    status: TaskStatus
    entry_count: int
    created_at: datetime


class KnowledgeBaseDetail(BaseModel):
    knowledge_base: KnowledgeBase
    entries: list[KnowledgeEntry]


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_url: str = Field(default="", max_length=500)


# ── 商机洞察 ──────────────────────────────────────────────────────────────


class KpiCard(BaseModel):
    key: str
    label: str
    value: int
    caption: str


class ChartPoint(BaseModel):
    label: str
    interaction: int
    opportunity: int


class ActivityItem(BaseModel):
    id: str
    title: str
    detail: str
    happened_at: datetime


class OpportunityItem(BaseModel):
    id: str
    company_name: str
    contact_name: str
    channel: str
    signal: str
    level: Literal["建议跟进", "初步信号", "暂无信号"]
    last_message_at: datetime
    summary: str


class OpportunityPage(BaseModel):
    range_label: str
    today_mined_count: int
    today_task_label: str
    follow_up_label: str
    kpis: list[KpiCard]
    chart: list[ChartPoint]
    activity: list[ActivityItem]
    analyzed_percent: int
    level_counts: dict[str, int]
    opportunities: list[OpportunityItem]


# ── LLM 接入状态 ──────────────────────────────────────────────────────────


class LlmRounds(BaseModel):
    """LLM 调用的累计计数。**进程内统计**，后端重启即归零。

    字段与 `app/llm/generator.py` 的 `GenerationStats.describe()` 一一对应。
    """

    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    total_tokens: int = 0
    cache_size: int = 0
    last_error_kind: str = ""
    last_error_message: str = ""


class LlmStatus(BaseModel):
    """LLM 接入的当前状态，回答「这批标准走的是 LLM 还是规则引擎，为什么」。

    `enabled` 与 `configured` 刻意分成两个字段：`enabled=true` 但没填密钥是
    最常见的配置错误，只有分开报，前端才能给出「已开启但缺少密钥」这种
    可操作的提示，而不是笼统地说「LLM 不可用」。

    字段与 `app/llm/config.py` 的 `LlmSettings.describe()` 对应，**不含密钥**。
    """

    enabled: bool
    configured: bool
    usable: bool
    model: str
    base_url: str
    timeout_seconds: int
    max_tokens: int
    judge_enabled: bool
    prompt_version: str
    # 提示词所在目录（可读标识）。提示词是仓库里的技能资产，可能被换掉，
    # 所以要和 prompt_version 一起报出来，才能回答「这批标准用的是哪份提示词」。
    prompt_dir: str
    # 人物模式有**另一份契约**（找人维度与会社不重叠），版本与目录单独报出，
    # 否则「找人列表的标准标签是 person-criteria/v1，会社状态接口却只报 criteria/v1」
    # 这类问题无从排查。
    person_prompt_version: str = ""
    person_prompt_dir: str = ""
    rounds: LlmRounds


# ── 工作空间设置 ──────────────────────────────────────────────────────────
class WorkspaceSettings(BaseModel):
    workspace_name: str
    default_channel: str
    default_count: int
    notify_on_reply: bool
    notify_weekly_digest: bool
    updated_at: datetime


class UpdateSettingsRequest(BaseModel):
    """局部更新：未提供的字段保持原值。"""

    workspace_name: str | None = Field(default=None, min_length=2, max_length=40)
    default_channel: str | None = None
    default_count: int | None = None
    notify_on_reply: bool | None = None
    notify_weekly_digest: bool | None = None

    @field_validator("workspace_name")
    @classmethod
    def workspace_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned == "":
            raise ValueError("工作空间名称不能为空")
        return cleaned

    @field_validator("default_channel")
    @classmethod
    def channel_must_be_supported(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in OUTREACH_CHANNELS:
            raise ValueError(f"不支持的触达渠道：{value}")
        return value

    @field_validator("default_count")
    @classmethod
    def count_must_be_selectable(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in COMPANY_COUNT_OPTIONS:
            raise ValueError(f"不支持的结果数量：{value}")
        return value
