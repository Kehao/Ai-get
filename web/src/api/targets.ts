import { request, upload } from './client';
import type {
  CompanyPage,
  CompanyQuery,
  Contact,
  CountOption,
  CreateListPayload,
  ListDetail,
  OutreachPlan,
  Strategy,
  TargetColumn,
  TargetCompany,
  TargetList,
  TargetOverview,
  UploadResult,
} from './types';

const buildQuery = (params: CompanyQuery): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const readStrategies = (): Promise<Strategy[]> => request<Strategy[]>('/targets/strategies');

export const readCountOptions = (): Promise<CountOption[]> => request<CountOption[]>('/targets/count-options');

export const readOverview = (): Promise<TargetOverview> => request<TargetOverview>('/targets/lists');

export const createList = (payload: CreateListPayload): Promise<TargetList> =>
  request<TargetList>('/targets/lists', { method: 'POST', body: payload });

export const uploadList = (file: File): Promise<UploadResult> => upload<UploadResult>('/targets/lists/upload', file);

export const readListDetail = (listId: string, params: CompanyQuery = {}): Promise<ListDetail> =>
  request<ListDetail>(`/targets/lists/${listId}${buildQuery(params)}`);

export const readCompanies = (listId: string, params: CompanyQuery = {}): Promise<CompanyPage> =>
  request<CompanyPage>(`/targets/lists/${listId}/companies${buildQuery(params)}`);

export const addColumn = (listId: string, name: string): Promise<TargetColumn> =>
  request<TargetColumn>(`/targets/lists/${listId}/columns`, { method: 'POST', body: { name } });

export const addMoreCompanies = (listId: string, count: number): Promise<TargetList> =>
  request<TargetList>(`/targets/lists/${listId}/more`, { method: 'POST', body: { count } });

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

export const deleteList = (listId: string): Promise<void> =>
  request<void>(`/targets/lists/${listId}`, { method: 'DELETE' });
