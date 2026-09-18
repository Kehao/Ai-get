// 知识库列表：把官网整理成知识库问答集，用于智能体的企业知识训练。

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, ExternalLink, Plus, Trash2 } from 'lucide-react';

import * as knowledgeApi from '@/api/knowledge';
import type { KnowledgeBase } from '@/api/types';
import Button from '@/components/Button';
import EmptyState from '@/components/EmptyState';
import Modal from '@/components/Modal';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatRelativeTime, toDisplayDomain } from '@/utils/format';

import styles from './KnowledgePage.module.less';

const STATUS_TONES = { failed: 'danger', running: 'warning', completed: 'success', pending: 'neutral' } as const;
const STATUS_LABELS = { failed: '失败', running: '生成中', completed: '已完成', pending: '排队中' } as const;

const KnowledgePage = (): JSX.Element => {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [saving, setSaving] = useState(false);

  const bases = useAsync(() => knowledgeApi.readKnowledgeBases());

  const openCreate = (): void => {
    setCreating(true);
    setName('');
    setSourceUrl('');
  };

  const handleCreate = async (): Promise<void> => {
    if (name.trim() === '') {
      showToast('请填写知识库名称', 'error');
      return;
    }
    if (sourceUrl.trim() === '') {
      showToast('请填写来源地址', 'error');
      return;
    }

    setSaving(true);
    try {
      const created = await knowledgeApi.createKnowledgeBase(name.trim(), sourceUrl.trim());
      showToast('知识库已创建，已生成问答条目', 'success');
      setCreating(false);
      navigate(ROUTES.consoleKnowledgeDetail(created.knowledge_base.id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '创建知识库失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (base: KnowledgeBase): Promise<void> => {
    try {
      await knowledgeApi.deleteKnowledgeBase(base.id);
      showToast('知识库已删除', 'success');
      bases.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  const items = bases.data ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerIcon}>
          <BookOpen size={20} />
        </span>
        <div className={styles.headerText}>
          <h1 className={styles.title}>知识库</h1>
          <p className={styles.subtitle}>知识库系统 · 把官网整理成知识库问答集，用于智能体的企业知识训练。</p>
        </div>

        <Button variant="primary" leadingIcon={<Plus size={15} />} onClick={openCreate}>
          新建知识库
        </Button>
      </header>

      {bases.loading ? (
        <div className={styles.loading}>
          <Spinner size={20} />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<BookOpen size={30} />}
          title="还没有知识库"
          description="先新建一个知识库，配置来源和知识库素材后，生成结果会直接保存到知识库。"
          action={
            <Button variant="primary" leadingIcon={<Plus size={15} />} onClick={openCreate}>
              新建知识库
            </Button>
          }
        />
      ) : (
        <div className={styles.grid}>
          {items.map((base) => (
            <article key={base.id} className={styles.card}>
              <button
                type="button"
                className={styles.cardBody}
                onClick={() => navigate(ROUTES.consoleKnowledgeDetail(base.id))}
              >
                <span className={styles.cardHeading}>
                  <h2 className={styles.cardName}>{base.name}</h2>
                  <Tag tone={STATUS_TONES[base.status]}>{STATUS_LABELS[base.status]}</Tag>
                </span>

                <span className={styles.source}>
                  <ExternalLink size={13} />
                  {toDisplayDomain(base.source_url)}
                </span>

                <span className={styles.cardMeta}>
                  <strong>{base.entry_count}</strong> 条问答
                  <span className={styles.dot}>·</span>
                  {formatRelativeTime(base.created_at)}
                </span>
              </button>

              <div className={styles.cardActions}>
                <Button
                  variant="ghost"
                  size="sm"
                  leadingIcon={<Trash2 size={14} />}
                  onClick={() => void handleDelete(base)}
                >
                  删除
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}

      <Modal
        open={creating}
        title="新建知识库"
        description="填写名称与来源地址，系统会抓取官网内容并生成问答集。"
        width={520}
        onClose={() => setCreating(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
            <Button variant="primary" loading={saving} onClick={() => void handleCreate()}>
              创建知识库
            </Button>
          </>
        }
      >
        <div className={styles.form}>
          <label className={styles.field}>
            <span className={styles.label}>名称</span>
            <input
              className={styles.input}
              value={name}
              placeholder="例如：Ai-get 官网知识库"
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>来源地址</span>
            <input
              className={styles.input}
              value={sourceUrl}
              placeholder="https://your-company.com"
              onChange={(event) => setSourceUrl(event.target.value)}
            />
            <span className={styles.fieldHint}>建议使用产品介绍或常见问题页面。</span>
          </label>
        </div>
      </Modal>
    </div>
  );
};

export default KnowledgePage;
