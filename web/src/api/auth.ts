import { request } from './client';
import type { LoginResponse, StatusMessage, User } from './types';

export const login = (email: string, password: string): Promise<LoginResponse> =>
  request<LoginResponse>('/auth/login', { method: 'POST', body: { email, password } });

export const register = (email: string, password: string): Promise<LoginResponse> =>
  request<LoginResponse>('/auth/register', { method: 'POST', body: { email, password } });

export const readCurrentUser = (): Promise<User> => request<User>('/auth/me');

export const logout = (): Promise<StatusMessage> => request<StatusMessage>('/auth/logout', { method: 'POST' });
