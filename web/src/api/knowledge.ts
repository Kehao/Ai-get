import { request } from './client';
import type { KnowledgeBase, KnowledgeBaseDetail } from './types';

export const readKnowledgeBases = (): Promise<KnowledgeBase[]> => request<KnowledgeBase[]>('/knowledge');

export const createKnowledgeBase = (name: string, sourceUrl: string): Promise<KnowledgeBaseDetail> =>
  request<KnowledgeBaseDetail>('/knowledge', { method: 'POST', body: { name, source_url: sourceUrl } });

export const readKnowledgeBase = (knowledgeBaseId: string): Promise<KnowledgeBaseDetail> =>
  request<KnowledgeBaseDetail>(`/knowledge/${knowledgeBaseId}`);

export const deleteKnowledgeBase = (knowledgeBaseId: string): Promise<void> =>
  request<void>(`/knowledge/${knowledgeBaseId}`, { method: 'DELETE' });
