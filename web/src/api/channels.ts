import { request } from './client';
import type { Channel, ConnectPage } from './types';

export const readChannels = (): Promise<ConnectPage> => request<ConnectPage>('/channels');

export const connectChannel = (channelId: string, accountLabel: string): Promise<Channel> =>
  request<Channel>(`/channels/${channelId}/connect`, { method: 'POST', body: { account_label: accountLabel } });

export const disconnectChannel = (channelId: string): Promise<Channel> =>
  request<Channel>(`/channels/${channelId}/connect`, { method: 'DELETE' });
