// 偏好设置的本地保存。
// 用 localStorage 而不是 sessionStorage：主题与语言属于长期偏好，重新打开也应保留。

export type ThemeMode = 'light' | 'dark' | 'system';
export type Language = 'zh-CN' | 'en';

const THEME_KEY = 'ai-get.theme';
const LANGUAGE_KEY = 'ai-get.language';

const THEME_MODES: ThemeMode[] = ['light', 'dark', 'system'];
const LANGUAGES: Language[] = ['zh-CN', 'en'];

export const DEFAULT_THEME: ThemeMode = 'system';
export const DEFAULT_LANGUAGE: Language = 'zh-CN';

const read = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};

const write = (key: string, value: string): void => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // 隐私模式下 localStorage 可能不可用，此时退化为仅当前会话生效
  }
};

export const readTheme = (): ThemeMode => {
  const stored = read(THEME_KEY);
  return THEME_MODES.find((mode) => mode === stored) ?? DEFAULT_THEME;
};

export const writeTheme = (mode: ThemeMode): void => write(THEME_KEY, mode);

export const readLanguage = (): Language => {
  const stored = read(LANGUAGE_KEY);
  return LANGUAGES.find((language) => language === stored) ?? DEFAULT_LANGUAGE;
};

export const writeLanguage = (language: Language): void => write(LANGUAGE_KEY, language);
