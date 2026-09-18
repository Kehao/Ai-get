// 表格分页：与参考站点一致，展示「当前页 / 总页数」与总数。

import { ChevronLeft, ChevronRight } from 'lucide-react';

import styles from './Pagination.module.less';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

const Pagination = ({ page, pageSize, total, onChange }: PaginationProps): JSX.Element | null => {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) {
    return null;
  }

  const go = (target: number): void => {
    const clamped = Math.min(Math.max(1, target), pageCount);
    if (clamped !== page) {
      onChange(clamped);
    }
  };

  return (
    <div className={styles.pagination}>
      <span className={styles.total}>共 {total} 条</span>
      <button type="button" className={styles.nav} disabled={page <= 1} onClick={() => go(page - 1)} aria-label="上一页">
        <ChevronLeft size={15} />
      </button>
      <span className={styles.indicator}>
        {page} / {pageCount}
      </span>
      <button
        type="button"
        className={styles.nav}
        disabled={page >= pageCount}
        onClick={() => go(page + 1)}
        aria-label="下一页"
      >
        <ChevronRight size={15} />
      </button>
    </div>
  );
};

export default Pagination;
