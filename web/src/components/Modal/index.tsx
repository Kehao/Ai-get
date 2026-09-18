// 通用弹窗：遮罩点击与 Esc 关闭，内容超出时内部滚动。

import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';

import styles from './Modal.module.less';

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  width?: number;
  footer?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

const Modal = ({ open, title, description, width = 520, footer, onClose, children }: ModalProps): JSX.Element | null => {
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeydown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeydown);
    return () => window.removeEventListener('keydown', handleKeydown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className={styles.mask} onClick={onClose} role="presentation">
      <div
        className={styles.dialog}
        style={{ width }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className={styles.header}>
          <div>
            <h2 className={styles.title}>{title}</h2>
            {description ? <p className={styles.description}>{description}</p> : null}
          </div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </header>

        <div className={styles.body}>{children}</div>

        {footer ? <footer className={styles.footer}>{footer}</footer> : null}
      </div>
    </div>
  );
};

export default Modal;
