// 分段控制器：用于「找公司 / 找人」「7 天 / 30 天 / 12 个月」这类互斥切换。

import type { ReactNode } from 'react';

import styles from './SegmentedControl.module.less';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface SegmentedControlProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'md' | 'lg';
  ariaLabel?: string;
}

const SegmentedControl = <T extends string>({
  options,
  value,
  onChange,
  size = 'md',
  ariaLabel,
}: SegmentedControlProps<T>): JSX.Element => (
  <div className={[styles.group, styles[size]].join(' ')} role="radiogroup" aria-label={ariaLabel}>
    {options.map((option) => {
      const selected = option.value === value;
      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={selected}
          className={[styles.item, selected ? styles.active : ''].filter(Boolean).join(' ')}
          onClick={() => onChange(option.value)}
        >
          {option.icon}
          <span>{option.label}</span>
        </button>
      );
    })}
  </div>
);

export default SegmentedControl;
