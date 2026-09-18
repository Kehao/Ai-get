// 会话令牌的本地保存。
// 用 sessionStorage 而不是 localStorage：关闭标签页即失效，避免长期驻留的凭证。

const TOKEN_KEY = 'ai-get.token';
const EMAIL_KEY = 'ai-get.email';

export const readToken = (): string | null => {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const writeToken = (token: string, email: string): void => {
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
    window.sessionStorage.setItem(EMAIL_KEY, email);
  } catch {
    // 隐私模式下 sessionStorage 可能不可用，此时退化为仅本次会话内存保存
  }
};

export const readEmail = (): string | null => {
  try {
    return window.sessionStorage.getItem(EMAIL_KEY);
  } catch {
    return null;
  }
};

export const clearToken = (): void => {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(EMAIL_KEY);
  } catch {
    // 同上，忽略存储不可用的情况
  }
};
