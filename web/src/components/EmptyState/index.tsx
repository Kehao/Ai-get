// 空状态：列表无数据时统一展示，避免每个页面各写一套。

import type { ReactNode } from 'react';
import { Inbox } from 'lucide-react';

import styles from './EmptyState.module.less';

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}

const EmptyState = ({ title, description, icon, action, compact = false }: EmptyStateProps): JSX.Element => (
  <div className={[styles.empty, compact ? styles.compact : ''].filter(Boolean).join(' ')}>
    <div className={styles.icon}>{icon ?? <Inbox size={compact ? 22 : 30} />}</div>
    <h3 className={styles.title}>{title}</h3>
    {description ? <p className={styles.description}>{description}</p> : null}
    {action ? <div className={styles.action}>{action}</div> : null}
  </div>
);

export default EmptyState;
