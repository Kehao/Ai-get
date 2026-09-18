import { request } from './client';
import type { ResearchDetail, ResearchPage, ResearchRecord } from './types';

export const readQuestions = (): Promise<string[]> => request<string[]>('/research/questions');

export const readRecords = (): Promise<ResearchPage> => request<ResearchPage>('/research/records');

export const createRecord = (query: string): Promise<ResearchRecord> =>
  request<ResearchRecord>('/research/records', { method: 'POST', body: { query } });

export const readRecord = (recordId: string): Promise<ResearchDetail> =>
  request<ResearchDetail>(`/research/records/${recordId}`);

export const deleteRecord = (recordId: string): Promise<void> =>
  request<void>(`/research/records/${recordId}`, { method: 'DELETE' });
