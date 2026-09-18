// 训练智能体：我的 AI 团队与系统模板。

import { useMemo, useState } from 'react';
import { Bot, Plus, Search, Sparkles, Trash2, Users } from 'lucide-react';

import * as agentsApi from '@/api/agents';
import type { Agent, AgentTemplate } from '@/api/types';
import Button from '@/components/Button';
import EmptyState from '@/components/EmptyState';
import Modal from '@/components/Modal';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { OUTREACH_CHANNELS } from '@/constants/channels';
import { useAsync } from '@/hooks/useAsync';
import { formatRelativeTime } from '@/utils/format';

import styles from './AgentConfigPage.module.less';

const EMOJI_OPTIONS = ['🤖', '🧠', '💼', '💬', '✉️', '🎯', '🚀', '🦾'];

interface AgentDraft {
  name: string;
  description: string;
  emoji: string;
  channels: string[];
  templateId?: string;
}

const EMPTY_DRAFT: AgentDraft = { name: '', description: '', emoji: '🤖', channels: ['邮件'] };

const AgentConfigPage = (): JSX.Element => {
  const { showToast } = useToast();

  const [keyword, setKeyword] = useState('');
  const [draft, setDraft] = useState<AgentDraft | null>(null);
  const [saving, setSaving] = useState(false);

  const agents = useAsync(() => agentsApi.readAgents());
  const templates = useAsync(() => agentsApi.readTemplates());

  const myAgents = agents.data ?? [];

  const visibleAgents = useMemo(() => {
    const trimmed = keyword.trim().toLowerCase();
    if (trimmed === '') {
      return myAgents;
    }
    return myAgents.filter(
      (agent) =>
        agent.name.toLowerCase().includes(trimmed) || agent.description.toLowerCase().includes(trimmed),
    );
  }, [myAgents, keyword]);

  const openBlankDraft = (): void => setDraft({ ...EMPTY_DRAFT });

  const openTemplateDraft = (template: AgentTemplate): void =>
    setDraft({
      name: template.name.replace('REVOR', 'Ai-get'),
      description: template.description,
      emoji: template.emoji,
      channels: [...template.channels],
      templateId: template.id,
    });

  const toggleChannel = (channel: string): void =>
    setDraft((current) => {
      if (current === null) {
        return current;
      }
      const hasChannel = current.channels.includes(channel);
      return {
        ...current,
        channels: hasChannel ? current.channels.filter((item) => item !== channel) : [...current.channels, channel],
      };
    });

  const handleCreate = async (): Promise<void> => {
    if (draft === null) {
      return;
    }
    if (draft.name.trim() === '') {
      showToast('请填写智能体名称', 'error');
      return;
    }
    if (draft.channels.length === 0) {
      showToast('请至少选择一个触达渠道', 'error');
      return;
    }

    setSaving(true);
    try {
      await agentsApi.createAgent({
        name: draft.name.trim(),
        description: draft.description.trim(),
        emoji: draft.emoji,
        channels: draft.channels,
        template_id: draft.templateId,
      });
      showToast('智能体已创建', 'success');
      setDraft(null);
      agents.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '创建智能体失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async (agent: Agent): Promise<void> => {
    try {
      await agentsApi.publishAgent(agent.id);
      showToast('智能体已发布', 'success');
      agents.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '发布失败', 'error');
    }
  };

  const handleDelete = async (agent: Agent): Promise<void> => {
    try {
      await agentsApi.deleteAgent(agent.id);
      showToast('智能体已删除', 'success');
      agents.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerIcon}>
          <Users size={20} />
        </span>
        <div className={styles.headerText}>
          <h1 className={styles.title}>我的 AI 团队</h1>
          <p className={styles.subtitle}>管理我的 AI 团队</p>
        </div>

        <label className={styles.search}>
          <Search size={15} />
          <input
            className={styles.searchInput}
            placeholder="搜索智能体"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </label>

        <Button variant="primary" leadingIcon={<Plus size={15} />} onClick={openBlankDraft}>
          创建智能体
        </Button>
      </header>

      <section className={styles.section}>
        <header className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>我的智能体</h2>
          <span className={styles.sectionCount}>{myAgents.length}</span>
          <span className={styles.sectionHint}>你创建的智能体会出现在这里</span>
        </header>

        {agents.loading ? (
          <div className={styles.loading}>
            <Spinner size={20} />
          </div>
        ) : visibleAgents.length === 0 ? (
          <EmptyState
            icon={<Bot size={30} />}
            title={keyword.trim() === '' ? '还没有自定义智能体' : '没有匹配的智能体'}
            description={
              keyword.trim() === ''
                ? '来创建你的第一个智能体吧！点击「创建智能体」开始。'
                : '换一个关键词试试，或直接创建新的智能体。'
            }
            action={
              <Button variant="primary" leadingIcon={<Plus size={15} />} onClick={openBlankDraft}>
                创建智能体
              </Button>
            }
          />
        ) : (
          <div className={styles.cardGrid}>
            {visibleAgents.map((agent) => (
              <article key={agent.id} className={styles.agentCard}>
                <div className={styles.agentTop}>
                  <span className={styles.agentEmoji}>{agent.emoji}</span>
                  <div className={styles.agentHeading}>
                    <h3 className={styles.agentName}>{agent.name}</h3>
                    <span className={styles.agentMeta}>
                      <Tag tone="success">{agent.status_label}</Tag>
                      <span className={styles.metaText}>{formatRelativeTime(agent.created_at)}</span>
                    </span>
                  </div>
                </div>

                <p className={styles.agentDescription}>{agent.description || '暂无描述'}</p>

                <div className={styles.channelRow}>
                  {agent.channels.map((channel) => (
                    <Tag key={channel} tone="neutral" outline>
                      {channel}
                    </Tag>
                  ))}
                </div>

                <div className={styles.agentActions}>
                  <Button variant="outline" size="sm" onClick={() => void handlePublish(agent)}>
                    发布
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    leadingIcon={<Trash2 size={14} />}
                    onClick={() => void handleDelete(agent)}
                  >
                    删除
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <header className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>从模板创建</h2>
          <span className={styles.sectionCount}>{templates.data?.length ?? 0}</span>
          <span className={styles.sectionHint}>预设模板，开箱即用</span>
        </header>

        <div className={styles.cardGrid}>
          {(templates.data ?? []).map((template) => (
            <button
              key={template.id}
              type="button"
              className={styles.templateCard}
              onClick={() => openTemplateDraft(template)}
            >
              <div className={styles.agentTop}>
                <span className={styles.agentEmoji}>{template.emoji}</span>
                <div className={styles.agentHeading}>
                  <h3 className={styles.agentName}>{template.name}</h3>
                  <span className={styles.agentMeta}>
                    <Tag tone="primary">{template.badge}</Tag>
                    <Tag tone="success">{template.status_label}</Tag>
                  </span>
                </div>
              </div>

              <p className={styles.agentDescription}>{template.description}</p>

              <div className={styles.templateFooter}>
                <span className={styles.templateSource}>{template.source_label}</span>
                <span className={styles.channelRow}>
                  {template.channels.map((channel) => (
                    <Tag key={channel} tone="neutral" outline>
                      {channel}
                    </Tag>
                  ))}
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <Modal
        open={draft !== null}
        title={draft?.templateId === undefined ? '创建智能体' : '基于模板创建智能体'}
        description="智能体会按照你选择的渠道与话术风格执行首轮触达。"
        width={560}
        onClose={() => setDraft(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDraft(null)}>
              取消
            </Button>
            <Button variant="primary" loading={saving} leadingIcon={<Sparkles size={15} />} onClick={() => void handleCreate()}>
              创建
            </Button>
          </>
        }
      >
        <div className={styles.form}>
          <div className={styles.field}>
            <span className={styles.label}>图标</span>
            <div className={styles.emojiRow}>
              {EMOJI_OPTIONS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  className={[styles.emojiOption, draft?.emoji === emoji ? styles.emojiOptionActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setDraft((current) => (current === null ? current : { ...current, emoji }))}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>

          <label className={styles.field}>
            <span className={styles.label}>名称</span>
            <input
              className={styles.input}
              value={draft?.name ?? ''}
              placeholder="例如：华东区 SaaS 破冰智能体"
              onChange={(event) =>
                setDraft((current) => (current === null ? current : { ...current, name: event.target.value }))
              }
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>描述</span>
            <textarea
              className={styles.textarea}
              value={draft?.description ?? ''}
              placeholder="描述这个智能体的触达目标与表达风格"
              onChange={(event) =>
                setDraft((current) => (current === null ? current : { ...current, description: event.target.value }))
              }
            />
          </label>

          <div className={styles.field}>
            <span className={styles.label}>触达渠道</span>
            <div className={styles.channelRow}>
              {OUTREACH_CHANNELS.map((channel) => {
                const active = draft?.channels.includes(channel) ?? false;
                return (
                  <button
                    key={channel}
                    type="button"
                    className={[styles.channelOption, active ? styles.channelOptionActive : '']
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => toggleChannel(channel)}
                  >
                    {channel}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default AgentConfigPage;
