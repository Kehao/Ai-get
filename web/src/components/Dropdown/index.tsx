// 下拉菜单：点击展开、点击外部或 Esc 关闭。用于「更多操作」「结果数量」等场景。

import { useCallback, useState, type ReactNode } from 'react';

import { useDismiss } from '@/hooks/useDismiss';

import styles from './Dropdown.module.less';

export interface DropdownItem {
  key: string;
  label: string;
  description?: string;
  danger?: boolean;
  disabled?: boolean;
}

interface DropdownProps {
  trigger: (state: { open: boolean }) => ReactNode;
  items: DropdownItem[];
  onSelect: (key: string) => void;
  align?: 'start' | 'end';
  panelWidth?: number;
}

const Dropdown = ({ trigger, items, onSelect, align = 'end', panelWidth = 200 }: DropdownProps): JSX.Element => {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const containerRef = useDismiss(open, close);

  return (
    <div className={styles.container} ref={containerRef}>
      <div className={styles.trigger} onClick={() => setOpen((current) => !current)} role="presentation">
        {trigger({ open })}
      </div>

      {open ? (
        <div className={[styles.panel, align === 'end' ? styles.alignEnd : styles.alignStart].join(' ')} style={{ width: panelWidth }}>
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              className={[styles.item, item.danger ? styles.danger : ''].filter(Boolean).join(' ')}
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                onSelect(item.key);
              }}
            >
              <span className={styles.itemLabel}>{item.label}</span>
              {item.description ? <span className={styles.itemDescription}>{item.description}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default Dropdown;
