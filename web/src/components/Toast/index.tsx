// 轻量提示：用于操作结果反馈，替代浏览器 alert。

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { CheckCircle2, Info, XCircle } from 'lucide-react';

import styles from './Toast.module.less';

type ToastTone = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  showToast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DURATION_MS = 3200;

const TONE_ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

export const ToastProvider = ({ children }: { children: ReactNode }): JSX.Element => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((message: string, tone: ToastTone = 'info'): void => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, DURATION_MS);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.viewport} role="status" aria-live="polite">
        {toasts.map((item) => {
          const Icon = TONE_ICONS[item.tone];
          return (
            <div key={item.id} className={`${styles.toast} ${styles[item.tone]}`}>
              <Icon size={16} />
              <span>{item.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error('useToast 必须在 ToastProvider 内使用');
  }
  return context;
};
