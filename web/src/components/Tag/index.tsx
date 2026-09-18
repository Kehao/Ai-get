// 语义标签：用于匹配结论、任务状态、渠道状态等。色调集中在这里维护，避免各处硬编码颜色。

import type { ReactNode } from 'react';

import styles from './Tag.module.less';

export type TagTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

interface TagProps {
  tone?: TagTone;
  size?: 'sm' | 'md';
  outline?: boolean;
  children: ReactNode;
}

const Tag = ({ tone = 'neutral', size = 'sm', outline = false, children }: TagProps): JSX.Element => (
  <span
    className={[styles.tag, styles[tone], styles[size], outline ? styles.outline : ''].filter(Boolean).join(' ')}
  >
    {children}
  </span>
);

export default Tag;
