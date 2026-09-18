// 关联账号：把触达渠道连接到当前工作空间。
// 套餐升级不在本次实现范围内，点击「升级」只给出明确提示。

import { useState } from 'react';
import {
  Instagram,
  Linkedin,
  Mail,
  MessageCircle,
  Plug,
  Send,
  Sparkles,
  Unplug,
  type LucideIcon,
} from 'lucide-react';

import * as channelsApi from '@/api/channels';
import type { Channel } from '@/api/types';
import Button from '@/components/Button';
import EmptyState from '@/components/EmptyState';
import Modal from '@/components/Modal';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { useAsync } from '@/hooks/useAsync';

import styles from './ConnectPage.module.less';

const CHANNEL_ICONS: Record<string, LucideIcon> = {
  mail: Mail,
  linkedin: Linkedin,
  'message-circle': MessageCircle,
  instagram: Instagram,
  send: Send,
};

const ConnectPage = (): JSX.Element => {
  const { showToast } = useToast();

  const [connecting, setConnecting] = useState<Channel | null>(null);
  const [accountLabel, setAccountLabel] = useState('');
  const [busyChannelId, setBusyChannelId] = useState<string | null>(null);

  const page = useAsync(() => channelsApi.readChannels());
  const summary = page.data?.summary;

  const handleUpgrade = (): void => {
    showToast('演示环境未接入套餐购买流程，升级功能暂不可用', 'info');
  };

  const openConnect = (channel: Channel): void => {
    setConnecting(channel);
    setAccountLabel(channel.id === 'email-smtp' ? 'sales@ai-get.dev' : '');
  };

  const handleConnect = async (): Promise<void> => {
    if (connecting === null) {
      return;
    }
    setBusyChannelId(connecting.id);
    try {
      await channelsApi.connectChannel(connecting.id, accountLabel.trim());
      showToast(`${connecting.name} 已连接`, 'success');
      setConnecting(null);
      page.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '连接失败', 'error');
    } finally {
      setBusyChannelId(null);
    }
  };

  const handleDisconnect = async (channel: Channel): Promise<void> => {
    setBusyChannelId(channel.id);
    try {
      await channelsApi.disconnectChannel(channel.id);
      showToast(`${channel.name} 已断开连接`, 'success');
      page.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '断开连接失败', 'error');
    } finally {
      setBusyChannelId(null);
    }
  };

  const renderChannel = (channel: Channel): JSX.Element => {
    const Icon = CHANNEL_ICONS[channel.icon] ?? Plug;
    const busy = busyChannelId === channel.id;

    return (
      <article key={channel.id} className={styles.channelCard}>
        <span className={styles.channelIcon}>
          <Icon size={18} />
        </span>

        <div className={styles.channelBody}>
          <div className={styles.channelHeading}>
            <h3 className={styles.channelName}>{channel.name}</h3>
            {channel.state === 'connected' ? <Tag tone="success">已连接</Tag> : null}
            {channel.state === 'coming_soon' ? <Tag tone="neutral">即将支持</Tag> : null}
          </div>
          <p className={styles.channelDescription}>{channel.description}</p>
          {channel.account_label !== null ? (
            <p className={styles.channelAccount}>{channel.account_label}</p>
          ) : null}
        </div>

        <div className={styles.channelAction}>
          {channel.state === 'connected' ? (
            <Button
              variant="outline"
              size="sm"
              loading={busy}
              leadingIcon={<Unplug size={14} />}
              onClick={() => void handleDisconnect(channel)}
            >
              断开连接
            </Button>
          ) : null}

          {channel.state === 'available' ? (
            <Button
              variant="primary"
              size="sm"
              loading={busy}
              leadingIcon={<Plug size={14} />}
              onClick={() => openConnect(channel)}
            >
              连接
            </Button>
          ) : null}

          {channel.state === 'locked' ? (
            <>
              <span className={styles.lockNote}>
                <Tag tone="primary">{channel.required_plan ?? '付费版'}</Tag>
                升级后解锁
              </span>
              <Button variant="outline" size="sm" leadingIcon={<Sparkles size={14} />} onClick={handleUpgrade}>
                升级
              </Button>
            </>
          ) : null}
        </div>
      </article>
    );
  };

  if (page.loading) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在加载渠道…</span>
      </div>
    );
  }

  if (page.error !== null) {
    return <EmptyState title="渠道列表不可用" description={page.error} />;
  }

  const connectedTotal = (summary?.connected_email ?? 0) + (summary?.connected_social ?? 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerIcon}>
          <Plug size={20} />
        </span>
        <div className={styles.headerText}>
          <h1 className={styles.title}>账号连接</h1>
          <p className={styles.subtitle}>连接 Ai-get 用于触达联系人的渠道。</p>
        </div>

        <span className={styles.plan}>
          {summary?.plan_name ?? '免费版'} 套餐
        </span>
        <Button variant="outline" size="sm" leadingIcon={<Sparkles size={14} />} onClick={handleUpgrade}>
          升级
        </Button>
      </header>

      <section className={styles.summaryRow}>
        <article className={styles.summaryCard}>
          <span className={styles.summaryIcon}>
            <Mail size={16} />
          </span>
          <div>
            <h2 className={styles.summaryTitle}>邮箱账号</h2>
            <p className={styles.summaryValue}>
              {summary?.connected_email ?? 0} / {summary?.total_email ?? 0}
            </p>
          </div>
          <Tag tone={summary?.connected_email ? 'success' : 'neutral'}>
            {summary?.connected_email ? '已连接' : '未连接'}
          </Tag>
        </article>

        <article className={styles.summaryCard}>
          <span className={styles.summaryIcon}>
            <Linkedin size={16} />
          </span>
          <div>
            <h2 className={styles.summaryTitle}>社媒账号</h2>
            <p className={styles.summaryValue}>
              {summary?.connected_social ?? 0} / {summary?.total_social ?? 0}
            </p>
          </div>
          <Tag tone={summary?.connected_social ? 'success' : 'neutral'}>
            {summary?.connected_social ? '已连接' : '未连接'}
          </Tag>
        </article>
      </section>

      {connectedTotal === 0 ? (
        <p className={styles.hint}>还没有连接任何账号，先连接邮箱渠道即可开始触达。</p>
      ) : null}

      <div className={styles.groups}>
        {(page.data?.groups ?? []).map((group) => (
          <section key={group.group} className={styles.group}>
            <header className={styles.groupHeader}>
              <h2 className={styles.groupTitle}>{group.group}</h2>
              <span className={styles.groupCount}>{group.channels.length}</span>
            </header>

            <div className={styles.channelList}>{group.channels.map(renderChannel)}</div>
          </section>
        ))}
      </div>

      <Modal
        open={connecting !== null}
        title={connecting === null ? '' : `连接 ${connecting.name}`}
        description={connecting?.description}
        width={480}
        onClose={() => setConnecting(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConnecting(null)}>
              取消
            </Button>
            <Button
              variant="primary"
              loading={busyChannelId === connecting?.id}
              leadingIcon={<Plug size={15} />}
              onClick={() => void handleConnect()}
            >
              确认连接
            </Button>
          </>
        }
      >
        <label className={styles.field}>
          <span className={styles.label}>账号标识</span>
          <input
            className={styles.input}
            value={accountLabel}
            placeholder="用于标识该账号，例如 sales@yourcompany.com"
            onChange={(event) => setAccountLabel(event.target.value)}
          />
          <span className={styles.fieldHint}>留空时默认使用当前登录邮箱。</span>
        </label>
      </Modal>
    </div>
  );
};

export default ConnectPage;
