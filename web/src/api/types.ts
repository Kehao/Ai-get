// 与后端 Pydantic 模型一一对应的类型定义。字段名保持与接口返回一致，避免额外的转换层。

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';
export type FieldState = 'ready' | 'failed' | 'blocked';
export type MatchLevel = '明确符合' | '可能符合' | '待确认';
export type SearchMode = 'company' | 'people';
/** 挖掘任务阶段，与上游 Websets 的状态机保持一致。 */
export type MiningPhase = 'generating_criteria' | 'searching' | 'verifying' | 'completed';
/** 准入标准的产出路径：LLM 生成（'llm'），或内置规则引擎兜底（'rule'）。 */
export type CriteriaSource = 'llm' | 'rule';
export type ChannelState = 'available' | 'connected' | 'coming_soon';
export type OpportunityLevel = '建议跟进' | '初步信号' | '暂无信号';
export type OpportunityRange = '7d' | '30d' | '12m';

export interface User {
  id: string;
  email: string;
  display_name: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface StatusMessage {
  message: string;
}

export interface UploadResult {
  list_id: string;
  imported_rows: number;
}

// ── 潜客挖掘 ──────────────────────────────────────────────────────────────

export interface Strategy {
  id: string;
  text: string;
}

export interface CountOption {
  value: number;
}

export interface TargetCondition {
  id: string;
  text: string;
  color: string;
  /** 该条件的权重，决定它对「匹配度」的贡献大小。 */
  weight: number;
  /** 所属维度（geo / industry / size / funding / business / signal / reachability）。 */
  category: string;
  /** 判定口径：把标准翻译成一个可直接回答的问题。 */
  question: string;
}

/** 挖掘进度四元组，恒有 full ≤ qualified ≤ verified ≤ goal。 */
export interface MiningProgress {
  stage: MiningPhase;
  goal: number;
  verified: number;
  qualified: number;
  full: number;
  stop_reason: string | null;
}

/** 数据源自描述，用于说明「这批结果是谁给的」。 */
export interface SourceInfo {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  regions: string[];
  priority: number;
  cost_per_call: number;
  requires_credentials: boolean;
}

export interface StrategyGroup {
  id: string;
  title: string;
  description: string;
  examples: string[];
}

export interface TargetList {
  id: string;
  query: string;
  mode: SearchMode;
  status: TaskStatus;
  progress: number;
  requested_count: number;
  discovered_count: number;
  contact_count: number;
  condition_items: TargetCondition[];
  strategy_groups: StrategyGroup[];
  follow_up_plan: string | null;
  created_at: string;
  updated_at: string;
  /** 当前阶段；未提供时视为已完成。 */
  phase?: MiningPhase;
  /** 真实计数的进度四元组；任务未开始时为 null。 */
  progress_detail?: MiningProgress | null;
  source_id?: string;
  source_name?: string;
  /** 这批准入标准由哪条路径产出：LLM 生成，或内置规则引擎兜底。 */
  criteria_source?: CriteriaSource;
  /** 产出方的可读标签，如「LLM · criteria/v1 · deepseek-flash」。 */
  criteria_label?: string;
  /** 非空表示这批标准是「LLM 失败后退到规则引擎」的结果，值即失败原因。 */
  criteria_fallback_reason?: string;
}

export interface TargetCompany {
  id: string;
  company_name: string;
  website: string;
  industries: string[];
  ai_summary: string;
  summary_state: FieldState;
  match_level: MatchLevel;
  match_reason: string;
  contact_count: number;
  contact_state: FieldState;
  official_contact_state: FieldState;
  location: string;
  employees: string;
  funding_stage: string;
  created_at: string;
  custom_values: Record<string, string>;
  /** 加权匹配得分（0-100），列表按它倒序。 */
  score: number;
}

export interface ReferenceItem {
  title: string;
  url: string;
}

export type ConditionStatus = '符合' | '不确定' | '不符合';

/** 调研项的键：会社侧与人物侧各有一组，同一个模型同时装着两种模式的调研结果。 */
export type ResearchKey = 'contacts' | 'official_contact' | 'person_contact' | 'profile_completeness';

export interface ResearchResult {
  key: ResearchKey;
  title: string;
  state: FieldState;
  summary: string;
  evidence: string[];
}

export interface ConditionEvaluation {
  condition: string;
  status: ConditionStatus;
  reference_count: number;
  explanation: string;
  source_label: string;
  source_url: string;
  /** 该行对应标准的权重，与 condition 一起复现判定来源。 */
  weight: number;
  /** 这条结论的全部可回溯来源；为空时退回展示 source_label/source_url 单链接。 */
  references: ReferenceItem[];
}

/** 富化台账：哪个源补了什么字段。照面字段来自网页摘要，matched_title 供人工核对。 */
export interface EnrichmentLedger {
  source_id: string;
  source_label: string;
  fields: Record<string, string>;
}

export interface TargetCompanyDetail {
  company: TargetCompany;
  references: ReferenceItem[];
  outreach_note: string;
  outreach: OutreachPlan | null;
  research_results: ResearchResult[];
  evaluations: ConditionEvaluation[];
  enrichment?: EnrichmentLedger;
}

/**
 * 人物行。与 `TargetCompany` **结构不同**（人是姓名/职位/所属公司与档案地址，
 * 公司是行业/规模/融资/官网），所以是并列的两个接口，而不是一个接口里的可选字段——
 * 后者会让「这行到底缺字段还是字段为空」无法区分。
 */
export interface TargetPerson {
  id: string;
  name: string;
  name_local: string;
  title: string;
  company: string;
  company_domain: string;
  source_label: string;
  source_url: string;
  ai_summary: string;
  summary_state: FieldState;
  match_level: MatchLevel;
  match_reason: string;
  location: string;
  contact_count: number;
  contact_state: FieldState;
  created_at: string;
  custom_values: Record<string, string>;
  /** 加权匹配得分（0-100），列表按它倒序。 */
  score: number;
}

export interface TargetPersonDetail {
  person: TargetPerson;
  references: ReferenceItem[];
  outreach_note: string;
  outreach: OutreachPlan | null;
  research_results: ResearchResult[];
  evaluations: ConditionEvaluation[];
}

export interface UpdateConditionsPayload {
  query?: string;
  conditions: string[];
}

export interface TargetColumn {
  id: string;
  name: string;
  is_builtin: boolean;
  created_at: string;
}

export interface Contact {
  id: string;
  name: string;
  title: string;
  email: string;
  linkedin: string;
  phone: string;
  confidence: number;
}

export interface CompanyPage {
  items: TargetCompany[];
  total: number;
  page: number;
  page_size: number;
}

export interface PersonPage {
  items: TargetPerson[];
  total: number;
  page: number;
  page_size: number;
}

export interface TargetOverview {
  /** 已完成列表的结果行总数，公司行与人物行都算在内。 */
  row_count: number;
  running_count: number;
  list_count: number;
  lists: TargetList[];
}

/**
 * 列表详情。`companies` 与 `people` **恰有一个非空**，由 `target_list.mode` 决定：
 * 会社列表不返回人物行，人物列表不返回公司行，避免前端拿到「另一半是空数组还是不存在」的歧义。
 */
export interface ListDetail {
  target_list: TargetList;
  columns: TargetColumn[];
  companies: CompanyPage | null;
  people: PersonPage | null;
}

export interface OutreachStep {
  day_label: string;
  title: string;
  detail: string;
  channel: string;
}

export interface OutreachPlan {
  id: string;
  list_id: string;
  agent_name: string;
  channel: string;
  status_label: string;
  steps: OutreachStep[];
  created_at: string;
}

export interface CreateListPayload {
  query: string;
  mode: SearchMode;
  count: number;
}

/** 列表行的查询参数。公司行与人物行共用同一组（都是分页 + 关键词 + 匹配度 + 排序）。 */
export interface RowQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  match_level?: string;
  sort?: string;
}

// ── 企业背调 ──────────────────────────────────────────────────────────────

export interface ResearchRecord {
  id: string;
  query: string;
  title: string;
  status: TaskStatus;
  progress: number;
  card_count: number;
  conversation_turns: number;
  tool_calls: number;
  report_markdown: string;
  created_at: string;
  updated_at: string;
}

export interface ResearchMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tool_name: string | null;
}

export interface ResearchDetail {
  record: ResearchRecord;
  messages: ResearchMessage[];
}

export interface ResearchPage {
  report_count: number;
  running_count: number;
  records: ResearchRecord[];
}

// ── 智能体 ────────────────────────────────────────────────────────────────

export interface AgentTemplate {
  id: string;
  emoji: string;
  name: string;
  badge: string;
  status_label: string;
  description: string;
  mode_label: string;
  channels: string[];
  source_label: string;
}

export interface Agent {
  id: string;
  name: string;
  emoji: string;
  description: string;
  status_label: string;
  channels: string[];
  created_at: string;
}

export interface CreateAgentPayload {
  name: string;
  description: string;
  emoji: string;
  channels: string[];
  template_id?: string;
}

// ── 关联账号 ──────────────────────────────────────────────────────────────

export interface Channel {
  id: string;
  name: string;
  group: string;
  description: string;
  icon: string;
  state: ChannelState;
  account_label: string | null;
}

export interface ChannelGroup {
  group: string;
  channels: Channel[];
}

export interface ConnectSummary {
  connected_email: number;
  total_email: number;
  connected_social: number;
  total_social: number;
}

export interface ConnectPage {
  summary: ConnectSummary;
  groups: ChannelGroup[];
}

// ── 知识库 ────────────────────────────────────────────────────────────────

export interface KnowledgeEntry {
  id: string;
  question: string;
  answer: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  source_url: string;
  status: TaskStatus;
  entry_count: number;
  created_at: string;
}

export interface KnowledgeBaseDetail {
  knowledge_base: KnowledgeBase;
  entries: KnowledgeEntry[];
}

// ── 商机洞察 ──────────────────────────────────────────────────────────────

export interface KpiCard {
  key: string;
  label: string;
  value: number;
  caption: string;
}

export interface ChartPoint {
  label: string;
  interaction: number;
  opportunity: number;
}

export interface ActivityItem {
  id: string;
  title: string;
  detail: string;
  happened_at: string;
}

export interface OpportunityItem {
  id: string;
  company_name: string;
  contact_name: string;
  channel: string;
  signal: string;
  level: OpportunityLevel;
  last_message_at: string;
  summary: string;
}

export interface OpportunityPage {
  range_label: string;
  today_mined_count: number;
  today_task_label: string;
  follow_up_label: string;
  kpis: KpiCard[];
  chart: ChartPoint[];
  activity: ActivityItem[];
  analyzed_percent: number;
  level_counts: Record<string, number>;
  opportunities: OpportunityItem[];
}

// ── 工作空间设置 ──────────────────────────────────────────────────────────

export interface WorkspaceSettings {
  workspace_name: string;
  default_channel: string;
  default_count: number;
  notify_on_reply: boolean;
  notify_weekly_digest: boolean;
  updated_at: string;
}

/** 局部更新：只提交需要改动的字段。 */
export type UpdateSettingsPayload = Partial<
  Pick<
    WorkspaceSettings,
    'workspace_name' | 'default_channel' | 'default_count' | 'notify_on_reply' | 'notify_weekly_digest'
  >
>;
