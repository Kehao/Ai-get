// 横向滚动的 chip 条：隐藏原生滚动条、两端按需渐隐，内容放不下时自动向左循环滚动。
// 参考站的「推荐策略」「推荐问题」即此交互，抽成组件避免两处各写一套溢出检测与无缝循环。

import {
  Children,
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react';

import styles from './ChipScroller.module.less';

/** 自动向左滚动的速度（像素 / 秒）。 */
const MARQUEE_SPEED = 45;

/** 边界判定容差：亚像素宽度下 scrollLeft 取整会差一点点，不留余量会误判。 */
const EDGE_TOLERANCE = 1;

interface ChipScrollerProps {
  children: ReactNode;
  /** 附加到滚动轨道上的类名，用于设置本页特有的 gap 等。 */
  className?: string;
}

const ChipScroller = ({ children, className }: ChipScrollerProps): JSX.Element => {
  const trackRef = useRef<HTMLDivElement>(null);
  const sequenceRef = useRef<HTMLDivElement>(null);
  const periodRef = useRef(0);
  const previousWidthRef = useRef(0);
  const pausedRef = useRef(false);
  const [overflow, setOverflow] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [fadeStart, setFadeStart] = useState(false);
  const [fadeEnd, setFadeEnd] = useState(false);

  const marquee = overflow && !reducedMotion;

  // 无缝循环要靠把整排 chip 再复制一份、滚过第一份后瞬间回位。
  // 复制件的按钮同时从 Tab 序列里摘掉（配合 aria-hidden），否则键盘与读屏用户会走两遍。
  const duplicated = useMemo(
    () =>
      Children.map(children, (child) =>
        isValidElement(child)
          ? cloneElement(child as ReactElement<{ tabIndex?: number }>, { tabIndex: -1 })
          : child,
      ),
    [children],
  );

  const syncFades = useCallback((): void => {
    const track = trackRef.current;
    if (track === null) {
      return;
    }

    const maxScroll = track.scrollWidth - track.clientWidth;
    setFadeStart(track.scrollLeft > EDGE_TOLERANCE);
    setFadeEnd(maxScroll > EDGE_TOLERANCE && track.scrollLeft < maxScroll - EDGE_TOLERANCE);
  }, []);

  const measure = useCallback((): void => {
    const track = trackRef.current;
    const sequence = sequenceRef.current;
    if (track === null || sequence === null) {
      return;
    }

    // 判「一排 chip 放不放得下」要用单个序列的宽度，不能用轨道的 scrollWidth
    // ——后者在已复制一份之后会翻倍，永远像是放不下。
    const singleWidth = sequence.offsetWidth;

    // 宽度变了说明换了一批 chip（例如切换「找公司 / 找人」），回到开头，
    // 否则新列表会从上一批滚到的中间位置开始展示。窗口缩放不会改变这里，不会误重置。
    if (singleWidth !== previousWidthRef.current) {
      previousWidthRef.current = singleWidth;
      track.scrollLeft = 0;
    }

    setOverflow(singleWidth > track.clientWidth + EDGE_TOLERANCE);

    // 一个循环周期的位移 = 第二份起点 - 第一份起点，比手算 gap 稳（轨道 padding 也算进去了）
    const copies = track.children;
    periodRef.current =
      copies.length > 1
        ? (copies[1] as HTMLElement).offsetLeft - (copies[0] as HTMLElement).offsetLeft
        : 0;

    syncFades();
  }, [syncFades]);

  useEffect(() => {
    const track = trackRef.current;
    if (track === null) {
      return;
    }

    measure();

    // 容器宽度变化（窗口缩放）与 chip 数量变化（接口返回）都要重新测量。
    // 后一种情况下轨道自身宽度不变，ResizeObserver 不会触发，得靠 MutationObserver 兜住子树的 childList。
    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(track);
    const mutationObserver = new MutationObserver(measure);
    mutationObserver.observe(track, { childList: true, subtree: true });

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [measure]);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = (): void => setReducedMotion(query.matches);

    sync();
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);

  // 自动向左循环滚动：直接推进 scrollLeft，滚满一个周期就减去一个周期。
  // 因为内容复制了一份，回位处画面完全重合，看不出跳变。
  useEffect(() => {
    if (!marquee) {
      return;
    }

    const track = trackRef.current;
    if (track === null) {
      return;
    }

    measure();

    let frame = 0;
    let previous = 0;

    const step = (now: number): void => {
      frame = requestAnimationFrame(step);
      if (previous === 0) {
        previous = now;
        return;
      }

      // 切到后台标签页时 rAF 会停摆，回来时首帧的间隔可能是好几秒，
      // 不夹一下会看到整排 chip 突然平移一大段
      const elapsed = Math.min((now - previous) / 1000, 0.1);
      previous = now;

      const period = periodRef.current;
      if (pausedRef.current || period <= 0) {
        return;
      }

      let next = track.scrollLeft + MARQUEE_SPEED * elapsed;
      if (next >= period) {
        next -= period * Math.floor(next / period);
      }
      track.scrollLeft = next;
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [marquee, measure]);

  return (
    <div className={styles.wrapper}>
      <div
        ref={trackRef}
        className={[styles.track, className].filter(Boolean).join(' ')}
        // 循环滚动时两端始终有内容被裁在视野外，渐隐常驻；退回手动滚动时再按实际位置算
        data-fade-start={marquee || fadeStart}
        data-fade-end={marquee || fadeEnd}
        onScroll={marquee ? undefined : syncFades}
        // 悬停 / 按住 / 键盘聚焦时停下，否则移动中的 chip 基本点不中
        onPointerEnter={() => {
          pausedRef.current = true;
        }}
        onPointerLeave={() => {
          pausedRef.current = false;
        }}
        onPointerDown={() => {
          pausedRef.current = true;
        }}
        onPointerUp={() => {
          pausedRef.current = false;
        }}
        onFocusCapture={() => {
          pausedRef.current = true;
        }}
        onBlurCapture={() => {
          pausedRef.current = false;
        }}
      >
        <div className={styles.sequence} ref={sequenceRef}>
          {children}
        </div>
        {marquee ? (
          <div className={styles.sequence} aria-hidden="true">
            {duplicated}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default ChipScroller;
