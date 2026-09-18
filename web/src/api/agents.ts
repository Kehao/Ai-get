import { request } from './client';
import type { Agent, AgentTemplate, CreateAgentPayload } from './types';

export const readTemplates = (): Promise<AgentTemplate[]> => request<AgentTemplate[]>('/agents/templates');

export const readAgents = (): Promise<Agent[]> => request<Agent[]>('/agents');

export const createAgent = (payload: CreateAgentPayload): Promise<Agent> =>
  request<Agent>('/agents', { method: 'POST', body: payload });

export const publishAgent = (agentId: string): Promise<Agent> =>
  request<Agent>(`/agents/${agentId}/publish`, { method: 'POST' });

export const deleteAgent = (agentId: string): Promise<void> =>
  request<void>(`/agents/${agentId}`, { method: 'DELETE' });
