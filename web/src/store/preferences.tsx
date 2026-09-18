// 工作空间偏好：主题与语言。集中在这里，供账户菜单的快速开关与设置页共用同一份状态。

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  readLanguage,
  readTheme,
  writeLanguage,
  writeTheme,
  type Language,
  type ThemeMode,
} from '@/utils/preferences';

type ResolvedTheme = 'light' | 'dark';

interface PreferencesContextValue {
  theme: ThemeMode;
  /** theme 为 system 时按系统偏好解析出的实际主题。 */
  resolvedTheme: ResolvedTheme;
  setTheme: (mode: ThemeMode) => void;
  /** 在浅色与深色之间直接切换，用于菜单里的一键开关。 */
  toggleTheme: () => void;
  language: Language;
  setLanguage: (language: Language) => void;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

const DARK_QUERY = '(prefers-color-scheme: dark)';

const readSystemTheme = (): ResolvedTheme =>
  window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';

export const PreferencesProvider = ({ children }: { children: ReactNode }): JSX.Element => {
  const [theme, setThemeState] = useState<ThemeMode>(readTheme);
  const [language, setLanguageState] = useState<Language>(readLanguage);
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(readSystemTheme);

  // 跟随系统时监听系统偏好变化
  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY);
    const handleChange = (event: MediaQueryListEvent): void => setSystemTheme(event.matches ? 'dark' : 'light');
    query.addEventListener('change', handleChange);
    return () => query.removeEventListener('change', handleChange);
  }, []);

  const resolvedTheme: ResolvedTheme = theme === 'system' ? systemTheme : theme;

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  const setTheme = useCallback((mode: ThemeMode): void => {
    setThemeState(mode);
    writeTheme(mode);
  }, []);

  const toggleTheme = useCallback((): void => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setTheme]);

  const setLanguage = useCallback((next: Language): void => {
    setLanguageState(next);
    writeLanguage(next);
  }, []);

  const value = useMemo<PreferencesContextValue>(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme, language, setLanguage }),
    [theme, resolvedTheme, setTheme, toggleTheme, language, setLanguage],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
};

export const usePreferences = (): PreferencesContextValue => {
  const context = useContext(PreferencesContext);
  if (context === null) {
    throw new Error('usePreferences 必须在 PreferencesProvider 内使用');
  }
  return context;
};
