// 浮层关闭行为：点击容器外部或按 Esc 时关闭。
// Dropdown 与 AccountMenu 共用，避免两处各写一份事件监听。

import { useEffect, useRef, type RefObject } from 'react';

export const useDismiss = (open: boolean, onDismiss: () => void): RefObject<HTMLDivElement> => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent): void => {
      if (!containerRef.current?.contains(event.target as Node)) {
        onDismiss();
      }
    };
    const handleKeydown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onDismiss();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeydown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeydown);
    };
  }, [open, onDismiss]);

  return containerRef;
};
