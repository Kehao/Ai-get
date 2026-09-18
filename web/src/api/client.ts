// 统一的请求封装：注入令牌、解析 JSON、把错误规整成 ApiError。
// 用原生 fetch 而不引入 axios，减少一个运行时依赖。

import { clearToken, readToken } from '@/utils/storage';

const API_BASE = '/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

export const request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const token = readToken();
  const headers: Record<string, string> = { Accept: 'application/json' };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (response.status === 401) {
    clearToken();
    throw new ApiError(await readErrorMessage(response, '登录状态已失效，请重新登录'), 401);
  }

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response, '请求失败'), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
};

export const upload = async <T>(path: string, file: File): Promise<T> => {
  const token = readToken();
  const form = new FormData();
  form.append('file', file);

  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response, '上传失败'), response.status);
  }
  return (await response.json()) as T;
};

const readErrorMessage = async (response: Response, fallback: string): Promise<string> => {
  try {
    const payload: unknown = await response.json();
    if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
      const detail = (payload as { detail: unknown }).detail;
      if (typeof detail === 'string') {
        return detail;
      }
      // 校验类错误（422）的 detail 是错误列表，取第一条的可读描述
      if (Array.isArray(detail)) {
        const first = detail[0] as { msg?: unknown } | undefined;
        if (typeof first?.msg === 'string') {
          return first.msg.replace(/^Value error,\s*/, '');
        }
      }
    }
  } catch {
    // 响应体不是 JSON 时使用兜底文案
  }
  return fallback;
};

/** 把任意请求异常转换成可直接展示的文案。 */
export const describeError = (error: unknown): string => {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return '发生未知错误，请稍后重试';
};
