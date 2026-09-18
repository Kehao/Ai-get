// 加载指示器：纯 SVG，不额外引入动画库。

import styles from './Spinner.module.less';

interface SpinnerProps {
  size?: number;
  className?: string;
}

const Spinner = ({ size = 16, className }: SpinnerProps): JSX.Element => (
  <svg
    className={[styles.spinner, className ?? ''].filter(Boolean).join(' ')}
    width={size}
    height={size}
    viewBox="0 0 24 24"
    role="progressbar"
    aria-label="加载中"
  >
    <circle className={styles.track} cx="12" cy="12" r="9" fill="none" strokeWidth="3" />
    <circle className={styles.head} cx="12" cy="12" r="9" fill="none" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

export default Spinner;
