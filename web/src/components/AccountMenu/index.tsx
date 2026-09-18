// 账户菜单：邮箱标识 + 快速开关（主题、语言）+ 二级入口 + 退出登录。
// 结构对齐参考站：上半区是即时生效的开关，下半区是跳转入口。

import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  Globe,
  LogOut,
  MoonStar,
  Sun,
  type LucideIcon,
} from 'lucide-react';

import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { useDismiss } from '@/hooks/useDismiss';
import { usePreferences } from '@/store/preferences';
import type { Language } from '@/utils/preferences';

import styles from './AccountMenu.module.less';

const LANGUAGE_OPTIONS: { value: Language; label: string; available: boolean }[] = [
  { value: 'zh-CN', label: '简体中文', available: true },
  { value: 'en', label: 'English', available: false },
];

export interface AccountMenuLink {
  key: string;
  label: string;
  icon: LucideIcon;
  /** 在新标签页打开。 */
  external?: boolean;
  href: string;
}

interface AccountMenuProps {
  email: string;
  planName: string;
  links: AccountMenuLink[];
  onSignOut: () => void;
  /** 侧边栏收起时只保留头像，菜单面板改为浮在右侧。 */
  collapsed?: boolean;
}

const AccountMenu = ({ email, planName, links, onSignOut, collapsed = false }: AccountMenuProps): JSX.Element => {
  const { resolvedTheme, toggleTheme, language, setLanguage } = usePreferences();
  const { showToast } = useToast();

  const [open, setOpen] = useState(false);
  const [languageOpen, setLanguageOpen] = useState(false);
  const close = useCallback(() => {
    setOpen(false);
    setLanguageOpen(false);
  }, []);
  const containerRef = useDismiss(open, close);

  const currentLanguage = LANGUAGE_OPTIONS.find((option) => option.value === language);
  const isDark = resolvedTheme === 'dark';

  const handleLanguageSelect = (value: Language, available: boolean): void => {
    setLanguageOpen(false);
    if (!available) {
      showToast('演示环境暂只提供简体中文界面', 'info');
      return;
    }
    setLanguage(value);
  };

  return (
    <div className={styles.container} ref={containerRef}>
      <button
        type="button"
        className={[styles.trigger, open ? styles.triggerOpen : ''].filter(Boolean).join(' ')}
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className={styles.avatar}>{email.slice(0, 1).toUpperCase()}</span>
        {collapsed ? null : (
          <>
            <span className={styles.identity}>
              <strong className={styles.email}>{email}</strong>
              <small className={styles.plan}>{planName}</small>
            </span>
            <ChevronDown
              size={14}
              className={[styles.chevron, open ? styles.chevronOpen : ''].filter(Boolean).join(' ')}
            />
          </>
        )}
      </button>

      {open ? (
        <div className={[styles.panel, collapsed ? styles.panelFloating : ''].filter(Boolean).join(' ')} role="menu">
          <header className={styles.panelHeader}>
            <span className={styles.panelEmail}>{email}</span>
            <span className={styles.panelCaption}>快速开关</span>
          </header>

          <div className={styles.switchGroup}>
            <div className={styles.switchRow}>
              <span className={styles.switchLabel}>
                <MoonStar size={16} className={styles.switchIcon} />
                主题
              </span>
              <button
                type="button"
                className={styles.themeToggle}
                onClick={toggleTheme}
                aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
                title={isDark ? '切换到浅色主题' : '切换到深色主题'}
              >
                {isDark ? <Sun size={16} /> : <MoonStar size={16} />}
              </button>
            </div>

            <div className={styles.switchRow}>
              <span className={styles.switchLabel}>
                <Globe size={16} className={styles.switchIcon} />
                语言
              </span>
              <button
                type="button"
                className={styles.languageButton}
                onClick={() => setLanguageOpen((current) => !current)}
                aria-expanded={languageOpen}
              >
                <Globe size={14} />
                {currentLanguage?.label ?? '简体中文'}
                <ChevronDown
                  size={14}
                  className={[styles.chevron, languageOpen ? styles.chevronOpen : ''].filter(Boolean).join(' ')}
                />
              </button>
            </div>

            {languageOpen ? (
              <div className={styles.languageList}>
                {LANGUAGE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={styles.languageOption}
                    onClick={() => handleLanguageSelect(option.value, option.available)}
                  >
                    <span className={styles.languageLabel}>{option.label}</span>
                    {option.available ? (
                      language === option.value ? (
                        <Check size={14} className={styles.check} />
                      ) : null
                    ) : (
                      <Tag tone="neutral">即将支持</Tag>
                    )}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className={styles.linkGroup}>
            {links.map((link) => {
              const Icon = link.icon;
              const content = (
                <>
                  <Icon size={15} />
                  {link.label}
                  <ArrowUpRight size={14} className={styles.linkArrow} />
                </>
              );

              // 站内页面交给路由跳转，站外或需新窗口打开的用原生链接
              return link.external ? (
                <a
                  key={link.key}
                  className={styles.link}
                  href={link.href}
                  role="menuitem"
                  target="_blank"
                  rel="noreferrer"
                  onClick={close}
                >
                  {content}
                </a>
              ) : (
                <Link key={link.key} className={styles.link} to={link.href} role="menuitem" onClick={close}>
                  {content}
                </Link>
              );
            })}
          </div>

          <div className={styles.signOutGroup}>
            <button
              type="button"
              className={styles.signOut}
              role="menuitem"
              onClick={() => {
                close();
                onSignOut();
              }}
            >
              退出登录
              <LogOut size={15} />
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default AccountMenu;
