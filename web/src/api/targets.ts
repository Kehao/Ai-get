import { request, upload } from './client';
import type {
  CompanyPage,
  Contact,
  CountOption,
  CreateListPayload,
  ListDetail,
  OutreachPlan,
  PersonPage,
  RowQuery,
  SearchMode,
  SourceInfo,
  Strategy,
  TargetColumn,
  TargetCompany,
  TargetCompanyDetail,
  TargetList,
  TargetOverview,
  TargetPersonDetail,
  UpdateConditionsPayload,
  UploadResult,
} from './types';

const buildQuery = (params: RowQuery): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  const text = search.toString();
  return text ? `?${text}` : '';
};

/** 推荐策略随「找公司 / 找人」切换，两种模式各有一组提示词。 */
export const readStrategies = (mode: SearchMode): Promise<Strategy[]> =>
  request<Strategy[]>(`/targets/strategies?mode=${mode}`);

export const readCountOptions = (): Promise<CountOption[]> => request<CountOption[]>('/targets/count-options');

/** 当前注册的数据源清单，用于界面标注结果出处。 */
export const readSources = (): Promise<SourceInfo[]> => request<SourceInfo[]>('/targets/sources');

export const readOverview = (): Promise<TargetOverview> => request<TargetOverview>('/targets/lists');

export const createList = (payload: CreateListPayload): Promise<TargetList> =>
  request<TargetList>('/targets/lists', { method: 'POST', body: payload });

export const uploadList = (file: File): Promise<UploadResult> => upload<UploadResult>('/targets/lists/upload', file);

export const readListDetail = (listId: string, params: RowQuery = {}): Promise<ListDetail> =>
  request<ListDetail>(`/targets/lists/${listId}${buildQuery(params)}`);

export const readCompanies = (listId: string, params: RowQuery = {}): Promise<CompanyPage> =>
  request<CompanyPage>(`/targets/lists/${listId}/companies${buildQuery(params)}`);

/** 人物行的分页接口。与 `readCompanies` 并列，返回的是结构不同的人物行。 */
export const readPeople = (listId: string, params: RowQuery = {}): Promise<PersonPage> =>
  request<PersonPage>(`/targets/lists/${listId}/people${buildQuery(params)}`);

export const addColumn = (listId: string, name: string): Promise<TargetColumn> =>
  request<TargetColumn>(`/targets/lists/${listId}/columns`, { method: 'POST', body: { name } });

export const addMoreCompanies = (listId: string, count: number): Promise<TargetList> =>
  request<TargetList>(`/targets/lists/${listId}/more`, { method: 'POST', body: { count } });

export const updateConditions = (listId: string, payload: UpdateConditionsPayload): Promise<TargetList> =>
  request<TargetList>(`/targets/lists/${listId}/conditions`, { method: 'PATCH', body: payload });

export const remine = (listId: string): Promise<TargetList> =>
  request<TargetList>(`/targets/lists/${listId}/mine`, { method: 'POST' });

export const readCompanyDetail = (listId: string, rowId: string): Promise<TargetCompanyDetail> =>
  request<TargetCompanyDetail>(`/targets/lists/${listId}/companies/${rowId}`);

export const readPersonDetail = (listId: string, rowId: string): Promise<TargetPersonDetail> =>
  request<TargetPersonDetail>(`/targets/lists/${listId}/people/${rowId}`);

export const readOutreach = (listId: string): Promise<OutreachPlan | null> =>
  request<OutreachPlan | null>(`/targets/lists/${listId}/outreach`);

export const createOutreach = (listId: string, agentName: string, channel: string): Promise<OutreachPlan> =>
  request<OutreachPlan>(`/targets/lists/${listId}/outreach`, {
    method: 'POST',
    body: { agent_name: agentName, channel },
  });

export const readContacts = (listId: string, rowId: string): Promise<Contact[]> =>
  request<Contact[]>(`/targets/lists/${listId}/companies/${rowId}/contacts`);

export const retryField = (
  listId: string,
  rowId: string,
  field: 'summary' | 'contacts' | 'official_contact',
): Promise<TargetCompany> =>
  request<TargetCompany>(`/targets/lists/${listId}/companies/${rowId}/retry?field=${field}`, { method: 'POST' });

/** 深挖一行企业：后端抓网页、定位官网并用 LLM 补全档案。单次十几秒；
 *  LLM 不可用时接口仍是 200，失败原因在返回体 `dossier_state` / `dossier_reason` 里。 */
export const deepDive = (listId: string, rowId: string): Promise<TargetCompany> =>
  request<TargetCompany>(`/targets/lists/${listId}/companies/${rowId}/deep-dive`, { method: 'POST' });

/** 「智能发现」：走 discovery agent（检索 → 提炼 → 逐家深挖），约 1~2 分钟，
 *  产出一张每行都带完整档案的新列表。模型不可用时返回 503。 */
export const agentDiscover = (profile: string, count = 0): Promise<TargetList> =>
  request<TargetList>('/targets/agent-discover', { method: 'POST', body: { profile, count } });

export const deleteList = (listId: string): Promise<void> =>
  request<void>(`/targets/lists/${listId}`, { method: 'DELETE' });
