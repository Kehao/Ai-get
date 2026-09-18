import { request } from './client';
import type { UpdateSettingsPayload, WorkspaceSettings } from './types';

export const readSettings = (): Promise<WorkspaceSettings> => request<WorkspaceSettings>('/settings');

export const updateSettings = (payload: UpdateSettingsPayload): Promise<WorkspaceSettings> =>
  request<WorkspaceSettings>('/settings', { method: 'PATCH', body: payload });
