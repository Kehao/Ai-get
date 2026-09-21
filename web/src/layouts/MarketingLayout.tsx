// 落地页布局：吸顶导航 + 页脚。主 CTA「雇用 Ai-get」直接进入控制台主功能页。

import { Link, Outlet, useNavigate } from 'react-router-dom';
import { ChevronDown, Globe } from 'lucide-react';

import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import { CONSOLE_ENTRY, ROUTES } from '@/constants/routes';
import { useAuth } from '@/store/auth';

import styles from './MarketingLayout.module.less';

const PRODUCT_ITEMS = [
  { key: 'targets', label: '潜客挖掘', description: '用自然语言描述画像，实时发现匹配企业' },
  { key: 'research', label: '企业背调', description: '触达前先摸清经营、组织与采购习惯' },
  { key: 'agents', label: '智能体', description: '训练贴合你沟通风格的 AI 销售智能体' },
  { key: 'opportunities', label: '商机洞察', description: '统一查看互动、回复与值得跟进的线索' },
];

const RESOURCE_ITEMS = [
  { key: 'how', label: '如何运作', description: '从目标市场到已预约会议的完整链路' },
  { key: 'channels', label: '渠道能力', description: '邮件、LinkedIn 与 WhatsApp 三渠道协同' },
  { key: 'faq', label: '常见问题', description: '关于数据来源与线索质量的说明' },
];

const MarketingLayout = (): JSX.Element => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const goConsole = (): void => navigate(CONSOLE_ENTRY);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to={ROUTES.home} className={styles.brand}>
            <span className={styles.brandMark}>A</span>
            <span className={styles.brandText}>
              <strong>Ai-get</strong>
              <small>AI 智能获客平台</small>
            </span>
          </Link>

          <nav className={styles.nav}>
            <a className={styles.navLink} href="#how">
              如何运作
            </a>

            <Dropdown
              align="start"
              panelWidth={264}
              items={PRODUCT_ITEMS}
              onSelect={goConsole}
              trigger={({ open }) => (
                <button type="button" className={[styles.navLink, open ? styles.navLinkOpen : ''].filter(Boolean).join(' ')}>
                  产品
                  <ChevronDown size={14} />
                </button>
              )}
            />

            <Dropdown
              align="start"
              panelWidth={248}
              items={RESOURCE_ITEMS}
              onSelect={() => navigate(`${ROUTES.home}#how`)}
              trigger={({ open }) => (
                <button type="button" className={[styles.navLink, open ? styles.navLinkOpen : ''].filter(Boolean).join(' ')}>
                  资源中心
                  <ChevronDown size={14} />
                </button>
              )}
            />
          </nav>

          <div className={styles.actions}>
            <span className={styles.locale}>
              <Globe size={15} />
              简体中文
            </span>

            {user ? (
              <Button variant="outline" onClick={goConsole}>
                进入工作台
              </Button>
            ) : (
              <Button variant="ghost" onClick={() => navigate(ROUTES.signIn)}>
                登录
              </Button>
            )}

            <Button variant="gradient" leadingIcon={<span aria-hidden>👋</span>} onClick={goConsole}>
              雇用 Ai-get
            </Button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerBrand}>
            <span className={styles.brandMark}>A</span>
            <div>
              <strong>Ai-get</strong>
              <p>AI B2B 销售智能体 · 用实时市场信号发现并触达真实买家</p>
            </div>
          </div>

          <div className={styles.footerLinks}>
            <Link to={ROUTES.signIn}>登录</Link>
            <Link to={ROUTES.signUp}>注册</Link>
            <Link to={ROUTES.terms}>服务条款</Link>
            <Link to={ROUTES.privacy}>隐私政策</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default MarketingLayout;
