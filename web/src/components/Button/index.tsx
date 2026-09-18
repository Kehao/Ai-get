// 通用按钮。变体与尺寸通过 props 控制，避免在每个页面里重写一份按钮样式。

import type { ButtonHTMLAttributes, ReactNode } from 'react';

import Spinner from '@/components/Spinner';

import styles from './Button.module.less';

type ButtonVariant = 'primary' | 'outline' | 'ghost' | 'text' | 'gradient';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  block?: boolean;
  leadingIcon?: ReactNode;
}

const Button = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  block = false,
  leadingIcon,
  children,
  className,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps): JSX.Element => {
  const classes = [styles.button, styles[variant], styles[size], block ? styles.block : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  return (
    <button type={type} className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <Spinner size={14} /> : leadingIcon}
      {children ? <span>{children}</span> : null}
    </button>
  );
};

export default Button;
