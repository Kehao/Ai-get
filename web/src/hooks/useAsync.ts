// 通用数据加载 Hook：统一 loading / error / 重试 与可选的轮询。
// 页面只关心「取什么数据」，不重复写 useEffect + useState 组合。

import { useCallback, useEffect, useRef, useState } from 'react';

import { describeError } from '@/api/client';

interface UseAsyncOptions<T> {
  /** 大于 0 时按该间隔轮询刷新，用于进度类数据。 */
  pollIntervalMs?: number;
  /** 轮询的停止条件，返回 true 时停止轮询。 */
  shouldStopPolling?: (data: T | null) => boolean;
  /** 加载函数依赖的外部参数；变化时重新加载，避免用到过期的闭包值。 */
  deps?: readonly (string | number | boolean | null)[];
}

export interface AsyncResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export const useAsync = <T>(loader: () => Promise<T>, options: UseAsyncOptions<T> = {}): AsyncResult<T> => {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const dataRef = useRef<T | null>(null);
  const loaderRef = useRef(loader);
  const optionsRef = useRef(options);
  loaderRef.current = loader;
  optionsRef.current = options;

  // 依赖数组长度需要保持稳定，因此序列化成字符串参与比较
  const depsKey = JSON.stringify(options.deps ?? []);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let active = true;

    const run = async (): Promise<void> => {
      try {
        const result = await loaderRef.current();
        if (!active) {
          return;
        }
        dataRef.current = result;
        setData(result);
        setError(null);
      } catch (caught) {
        if (!active) {
          return;
        }
        setError(describeError(caught));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void run();

    const interval = optionsRef.current.pollIntervalMs ?? 0;
    const timer =
      interval > 0
        ? window.setInterval(() => {
            const shouldStop = optionsRef.current.shouldStopPolling;
            if (shouldStop?.(dataRef.current)) {
              return;
            }
            void run();
          }, interval)
        : undefined;

    return () => {
      active = false;
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
    };
  }, [reloadToken, depsKey]);

  return { data, loading, error, reload };
};
