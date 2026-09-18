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
ChannelState = Literal["available", "connected", "locked", "coming_soon"]


class User(BaseModel):
    id: str
    email: str
    display_name: str
    plan_name: str


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
    is_free: bool


class TargetList(BaseModel):
    id: str
    query: str
    mode: SearchMode
    status: TaskStatus
    progress: int
    requested_count: int
    discovered_count: int
    contact_count: int
    conditions: list[str]
    follow_up_plan: str | None
    created_at: datetime
    updated_at: datetime


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
    custom_values: dict[str, str] = Field(default_factory=dict)


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
    company_count: int
    running_count: int
    list_count: int
    lists: list[TargetList]


class CompanyPage(BaseModel):
    items: list[TargetCompany]
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
    target_list: TargetList
    columns: list[TargetColumn]
    companies: CompanyPage


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


class CreateOutreachRequest(BaseModel):
    agent_name: str = Field(default="REVOR 默认销售智能体", max_length=60)
    channel: str = Field(default="邮件", max_length=20)


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
    required_plan: str | None
    account_label: str | None


class ChannelGroup(BaseModel):
    group: str
    channels: list[Channel]


class ConnectSummary(BaseModel):
    plan_name: str
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
