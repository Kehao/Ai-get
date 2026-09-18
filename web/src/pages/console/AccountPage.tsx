// 用户中心：当前账号信息与工作空间数据概览。

import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, CircleUser, KeyRound, Settings } from 'lucide-react';

import * as agentsApi from '@/api/agents';
import * as channelsApi from '@/api/channels';
import * as knowledgeApi from '@/api/knowledge';
import * as researchApi from '@/api/research';
import * as targetsApi from '@/api/targets';
import EmptyState from '@/components/EmptyState';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { useAuth } from '@/store/auth';
import { formatNumber } from '@/utils/format';

import styles from './AccountPage.module.less';

interface AccountOverview {
  listCount: number;
  companyCount: number;
  reportCount: number;
  agentCount: number;
  knowledgeCount: number;
  connectedChannels: number;
  totalChannels: number;
}

/** 概览数据取自各业务接口，用户中心不额外引入聚合接口。 */
const loadOverview = async (): Promise<AccountOverview> => {
  const [targets, research, agents, knowledge, channels] = await Promise.all([
    targetsApi.readOverview(),
    researchApi.readRecords(),
    agentsApi.readAgents(),
    knowledgeApi.readKnowledgeBases(),
    channelsApi.readChannels(),
  ]);

  const { connected_email, connected_social, total_email, total_social } = channels.summary;

  return {
    listCount: targets.list_count,
    companyCount: targets.company_count,
    reportCount: research.report_count,
    agentCount: agents.length,
    knowledgeCount: knowledge.length,
    connectedChannels: connected_email + connected_social,
    totalChannels: total_email + total_social,
  };
};

const AccountPage = (): JSX.Element => {
  const { user } = useAuth();
  const overview = useAsync(loadOverview);

  if (user === null) {
    return <EmptyState title="未登录" description="请重新登录后再查看账号信息。" />;
  }

  const stats = overview.data;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.avatar}>{user.email.slice(0, 1).toUpperCase()}</span>
        <div className={styles.headerText}>
          <h1 className={styles.title}>{user.display_name}</h1>
          <p className={styles.subtitle}>{user.email}</p>
        </div>
        <Tag tone="primary" size="md">
          {user.plan_name}
        </Tag>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>账号信息</h2>

        <dl className={styles.infoGrid}>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>邮箱</dt>
            <dd className={styles.infoValue}>{user.email}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>显示名</dt>
            <dd className={styles.infoValue}>{user.display_name}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>账号 ID</dt>
            <dd className={styles.infoValue}>{user.id}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>登录方式</dt>
            <dd className={styles.infoValue}>
              <KeyRound size={14} />
              邮箱 + 密码
            </dd>
          </div>
        </dl>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>数据概览</h2>

        {overview.loading ? (
          <div className={styles.loading}>
            <Spinner size={20} />
          </div>
        ) : overview.error !== null ? (
          <EmptyState compact title="概览数据加载失败" description={overview.error} />
        ) : (
          <div className={styles.statGrid}>
            <StatCard label="潜客列表" value={formatNumber(stats?.listCount ?? 0)} caption="已创建的挖掘列表" />
            <StatCard label="潜客结果" value={formatNumber(stats?.companyCount ?? 0)} caption="累计发现的企业" />
            <StatCard label="背调报告" value={formatNumber(stats?.reportCount ?? 0)} caption="已完成的企业调研" />
            <StatCard label="智能体" value={formatNumber(stats?.agentCount ?? 0)} caption="自定义销售智能体" />
            <StatCard label="知识库" value={formatNumber(stats?.knowledgeCount ?? 0)} caption="用于训练的企业知识" />
            <StatCard
              label="已连渠道"
              value={`${stats?.connectedChannels ?? 0} / ${stats?.totalChannels ?? 0}`}
              caption="可用的触达渠道"
            />
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>快捷入口</h2>

        <div className={styles.shortcutGroup}>
          <Shortcut
            icon={<Settings size={17} />}
            title="工作空间设置"
            description="默认渠道、结果数量与通知偏好"
            to={ROUTES.consoleSettings}
          />
          <Shortcut
            icon={<BookOpen size={17} />}
            title="相关文档"
            description="从挖掘到触达的完整使用说明"
            to={ROUTES.docs}
            external
          />
          <Shortcut
            icon={<CircleUser size={17} />}
            title="关联账号"
            description="管理用于触达的邮箱与社媒渠道"
            to={ROUTES.consoleChannels}
          />
        </div>
      </section>
    </div>
  );
};

const StatCard = ({ label, value, caption }: { label: string; value: string; caption: string }): JSX.Element => (
  <article className={styles.statCard}>
    <span className={styles.statLabel}>{label}</span>
    <span className={styles.statValue}>{value}</span>
    <span className={styles.statCaption}>{caption}</span>
  </article>
);

const Shortcut = ({
  icon,
  title,
  description,
  to,
  external = false,
}: {
  icon: JSX.Element;
  title: string;
  description: string;
  to: string;
  external?: boolean;
}): JSX.Element => {
  const content = (
    <>
      <span className={styles.shortcutIcon}>{icon}</span>
      <span className={styles.shortcutText}>
        <strong>{title}</strong>
        <small>{description}</small>
      </span>
      <ArrowRight size={15} className={styles.shortcutArrow} />
    </>
  );

  if (external) {
    return (
      <a className={styles.shortcut} href={to} target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }
  return (
    <Link className={styles.shortcut} to={to}>
      {content}
    </Link>
  );
};

export default AccountPage;
