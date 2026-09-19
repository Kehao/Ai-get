// 横向滚动的 chip 条：隐藏原生滚动条，只在真正溢出的一侧做渐隐，用来提示还能继续滚动。
// 参考站的「推荐策略」「推荐问题」都是这个交互，抽成组件避免两处各写一套溢出检测。

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

import styles from './ChipScroller.module.less';

interface ChipScrollerProps {
  children: ReactNode;
  /** 附加到滚动轨道上的类名，用于设置本页特有的 gap 等。 */
  className?: string;
}

const ChipScroller = ({ children, className }: ChipScrollerProps): JSX.Element => {
  const trackRef = useRef<HTMLDivElement>(null);
  const [fadeStart, setFadeStart] = useState(false);
  const [fadeEnd, setFadeEnd] = useState(false);

  const syncEdges = useCallback((): void => {
    const track = trackRef.current;
    if (track === null) {
      return;
    }

    // 留 1px 容差：亚像素宽度下 scrollLeft 取整会差一点点，否则刚滚到头时仍以为还能滚
    const maxScroll = track.scrollWidth - track.clientWidth;
    setFadeStart(track.scrollLeft > 1);
    setFadeEnd(maxScroll > 1 && track.scrollLeft < maxScroll - 1);
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (track === null) {
      return;
    }

    syncEdges();

    // 容器宽度变化（窗口缩放）与 chip 数量变化（接口返回）都要重新测量。
    // 轨道自身宽度由布局决定、内容变化不会触发 ResizeObserver，所以另挂一个 MutationObserver 兜住后一种情况。
    const resizeObserver = new ResizeObserver(syncEdges);
    resizeObserver.observe(track);
    const mutationObserver = new MutationObserver(syncEdges);
    mutationObserver.observe(track, { childList: true });

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [syncEdges]);

  return (
    <div className={styles.wrapper}>
      <div
        ref={trackRef}
        className={[styles.track, className].filter(Boolean).join(' ')}
        data-fade-start={fadeStart}
        data-fade-end={fadeEnd}
        onScroll={syncEdges}
      >
        {children}
      </div>
    </div>
  );
};

export default ChipScroller;
