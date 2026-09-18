// 与后端 Pydantic 模型一一对应的类型定义。字段名保持与接口返回一致，避免额外的转换层。

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';
export type FieldState = 'ready' | 'failed' | 'blocked';
export type MatchLevel = '明确符合' | '可能符合' | '待确认';
export type SearchMode = 'company' | 'people';
export type ChannelState = 'available' | 'connected' | 'locked' | 'coming_soon';
export type OpportunityLevel = '建议跟进' | '初步信号' | '暂无信号';
export type OpportunityRange = '7d' | '30d' | '12m';

export interface User {
  id: string;
  email: string;
  display_name: string;
  plan_name: string;
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
  is_free: boolean;
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
  conditions: string[];
  follow_up_plan: string | null;
  created_at: string;
  updated_at: string;
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
  custom_values: Record<string, string>;
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

export interface TargetOverview {
  company_count: number;
  running_count: number;
  list_count: number;
  lists: TargetList[];
}

export interface ListDetail {
  target_list: TargetList;
  columns: TargetColumn[];
  companies: CompanyPage;
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

export interface CompanyQuery {
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
  required_plan: string | null;
  account_label: string | null;
}

export interface ChannelGroup {
  group: string;
  channels: Channel[];
}

export interface ConnectSummary {
  plan_name: string;
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
