// 登录态管理。令牌持久化在 sessionStorage，用户信息在应用启动时通过 /auth/me 校验。

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import * as authApi from '@/api/auth';
import { ApiError } from '@/api/client';
import type { User } from '@/api/types';
import { clearToken, readToken, writeToken } from '@/utils/storage';

interface AuthContextValue {
  user: User | null;
  initializing: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider = ({ children }: { children: ReactNode }): JSX.Element => {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    let active = true;

    const restore = async (): Promise<void> => {
      if (!readToken()) {
        setInitializing(false);
        return;
      }
      try {
        const current = await authApi.readCurrentUser();
        if (active) {
          setUser(current);
        }
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          clearToken();
        }
      } finally {
        if (active) {
          setInitializing(false);
        }
      }
    };

    void restore();
    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string): Promise<void> => {
    const result = await authApi.login(email, password);
    writeToken(result.token, result.user.email);
    setUser(result.user);
  }, []);

  const signUp = useCallback(async (email: string, password: string): Promise<void> => {
    const result = await authApi.register(email, password);
    writeToken(result.token, result.user.email);
    setUser(result.user);
  }, []);

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout();
    } catch {
      // 退出登录失败不应阻塞用户离开，本地令牌照常清理
    }
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, initializing, signIn, signUp, signOut }),
    [user, initializing, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth 必须在 AuthProvider 内使用');
  }
  return context;
};
