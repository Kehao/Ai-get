// 控制台布局：可收起的侧边栏 + 内容区。
// 按需求不实现积分与安装 Skill 模块，因此侧边栏底部只保留套餐标识与账号菜单。

import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  CircleUser,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
} from 'lucide-react';

import AccountMenu, { type AccountMenuLink } from '@/components/AccountMenu';
import { CONSOLE_NAV } from '@/constants/navigation';
import { ROUTES } from '@/constants/routes';
import { useAuth } from '@/store/auth';

import styles from './ConsoleLayout.module.less';

const ACCOUNT_LINKS: AccountMenuLink[] = [
  { key: 'account', label: '用户中心', icon: CircleUser, href: ROUTES.consoleAccount },
  { key: 'settings', label: '设置', icon: Settings, href: ROUTES.consoleSettings },
  { key: 'docs', label: '相关文档', icon: BookOpen, href: ROUTES.docs, external: true },
];

const ConsoleLayout = (): JSX.Element => {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>(['agents']);

  // 进入某个分组下的页面时自动展开该分组
  useEffect(() => {
    const activeGroup = CONSOLE_NAV.find((item) =>
      item.children?.some((child) => location.pathname.startsWith(child.path)),
    );
    if (activeGroup) {
      setExpandedKeys((current) => (current.includes(activeGroup.key) ? current : [...current, activeGroup.key]));
    }
  }, [location.pathname]);

  const handleSignOut = async (): Promise<void> => {
    await signOut();
    navigate(ROUTES.signIn, { replace: true });
  };

  const toggleGroup = (key: string): void => {
    setExpandedKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  };

  return (
    <div className={[styles.shell, collapsed ? styles.collapsed : ''].filter(Boolean).join(' ')}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <Link to={ROUTES.consoleTargets} className={styles.brandLink}>
            <span className={styles.brandMark}>A</span>
            {collapsed ? null : (
              <span className={styles.brandText}>
                <strong>Ai-get</strong>
                <small>智能获客平台</small>
              </span>
            )}
          </Link>
          <button
            type="button"
            className={styles.collapseButton}
            onClick={() => setCollapsed((current) => !current)}
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <div className={styles.navScroll}>
          {collapsed ? null : <p className={styles.groupLabel}>功能</p>}

          <nav className={styles.nav}>
            {CONSOLE_NAV.map((item) => {
              const Icon = item.icon;
              const expanded = expandedKeys.includes(item.key);

              if (item.children) {
                const childActive = item.children.some((child) => location.pathname.startsWith(child.path));
                return (
                  <div key={item.key} className={styles.navGroup}>
                    <button
                      type="button"
                      className={[styles.navItem, childActive ? styles.navItemActive : ''].filter(Boolean).join(' ')}
                      onClick={() => (collapsed ? navigate(item.children?.[0]?.path ?? ROUTES.home) : toggleGroup(item.key))}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon size={17} className={styles.navIcon} />
                      {collapsed ? null : (
                        <>
                          <span className={styles.navLabel}>{item.label}</span>
                          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </>
                      )}
                    </button>

                    {expanded && !collapsed ? (
                      <div className={styles.subNav}>
                        {item.children.map((child) => (
                          <NavLink
                            key={child.path}
                            to={child.path}
                            className={({ isActive }) =>
                              [styles.subNavItem, isActive ? styles.subNavItemActive : ''].filter(Boolean).join(' ')
                            }
                          >
                            {child.label}
                          </NavLink>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              }

              return (
                <NavLink
                  key={item.key}
                  to={item.path ?? ROUTES.home}
                  className={({ isActive }) =>
                    [styles.navItem, isActive ? styles.navItemActive : ''].filter(Boolean).join(' ')
                  }
                  title={collapsed ? item.label : undefined}
                >
                  <Icon size={17} className={styles.navIcon} />
                  {collapsed ? null : <span className={styles.navLabel}>{item.label}</span>}
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className={styles.footer}>
          {collapsed ? null : <span className={styles.planBadge}>{user?.plan_name ?? '免费版'}</span>}

          <AccountMenu
            email={user?.email ?? '未登录'}
            planName={user?.plan_name ?? '免费版'}
            links={ACCOUNT_LINKS}
            collapsed={collapsed}
            onSignOut={() => void handleSignOut()}
          />
        </div>
      </aside>

      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  );
};

export default ConsoleLayout;
