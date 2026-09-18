// 进度条：挖掘进度与背调进度共用。

import styles from './ProgressBar.module.less';

interface ProgressBarProps {
  value: number;
  tone?: 'primary' | 'success';
  height?: number;
  showLabel?: boolean;
  label?: string;
}

const ProgressBar = ({
  value,
  tone = 'primary',
  height = 6,
  showLabel = false,
  label,
}: ProgressBarProps): JSX.Element => {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div className={styles.wrapper}>
      {showLabel ? (
        <div className={styles.header}>
          <span className={styles.label}>{label ?? '进度'}</span>
          <span className={styles.value}>{clamped}%</span>
        </div>
      ) : null}
      <div className={styles.track} style={{ height }} role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
        <div className={[styles.bar, styles[tone]].join(' ')} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
};

export default ProgressBar;
