// 开关控件：用于设置页的布尔项。语义上等价于 role="switch"，可键盘操作。

import styles from './Switch.module.less';

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}

const Switch = ({ checked, onChange, label, disabled = false }: SwitchProps): JSX.Element => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    className={[styles.switch, checked ? styles.on : ''].filter(Boolean).join(' ')}
    onClick={() => onChange(!checked)}
  >
    <span className={styles.knob} />
  </button>
);

export default Switch;
