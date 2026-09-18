// 知识库详情：展示由官网内容生成的问答条目。

import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink, MessageSquareQuote, Search, Trash2 } from 'lucide-react';

import * as knowledgeApi from '@/api/knowledge';
import Button from '@/components/Button';
import EmptyState from '@/components/EmptyState';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTime, toDisplayDomain } from '@/utils/format';

import styles from './KnowledgeDetailPage.module.less';

const STATUS_TONES = { failed: 'danger', running: 'warning', completed: 'success', pending: 'neutral' } as const;
const STATUS_LABELS = { failed: '失败', running: '生成中', completed: '已完成', pending: '排队中' } as const;

const KnowledgeDetailPage = (): JSX.Element => {
  const { knowledgeBaseId = '' } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [keyword, setKeyword] = useState('');

  const detail = useAsync(() => knowledgeApi.readKnowledgeBase(knowledgeBaseId), {
    deps: [knowledgeBaseId],
  });

  const base = detail.data?.knowledge_base;
  const entries = detail.data?.entries ?? [];

  const visibleEntries = useMemo(() => {
    const trimmed = keyword.trim().toLowerCase();
    if (trimmed === '') {
      return entries;
    }
    return entries.filter(
      (entry) =>
        entry.question.toLowerCase().includes(trimmed) || entry.answer.toLowerCase().includes(trimmed),
    );
  }, [entries, keyword]);

  const handleDelete = async (): Promise<void> => {
    if (base === undefined) {
      return;
    }
    try {
      await knowledgeApi.deleteKnowledgeBase(base.id);
      showToast('知识库已删除', 'success');
      navigate(ROUTES.consoleKnowledge, { replace: true });
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  if (detail.loading && base === undefined) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在加载知识库…</span>
      </div>
    );
  }

  if (detail.error !== null && base === undefined) {
    return (
      <EmptyState
        title="知识库不可用"
        description={detail.error}
        action={
          <Link to={ROUTES.consoleKnowledge}>
            <Button variant="outline">返回知识库</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <Link to={ROUTES.consoleKnowledge} className={styles.back}>
            <ArrowLeft size={15} />
            知识库
          </Link>

          <Button variant="ghost" size="sm" leadingIcon={<Trash2 size={14} />} onClick={() => void handleDelete()}>
            删除知识库
          </Button>
        </div>

        <h1 className={styles.title}>{base?.name}</h1>

        <div className={styles.headerMeta}>
          <Tag tone={STATUS_TONES[base?.status ?? 'pending']}>{STATUS_LABELS[base?.status ?? 'pending']}</Tag>
          <a className={styles.source} href={base?.source_url} target="_blank" rel="noreferrer">
            <ExternalLink size={13} />
            {toDisplayDomain(base?.source_url ?? '')}
          </a>
          <span className={styles.metaText}>
            <strong>{entries.length}</strong> 条问答
          </span>
          {base ? <span className={styles.metaText}>创建于 {formatDateTime(base.created_at)}</span> : null}
        </div>
      </header>

      <section className={styles.section}>
        <header className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>问答条目</h2>

          <label className={styles.search}>
            <Search size={15} />
            <input
              className={styles.searchInput}
              placeholder="搜索问题或答案"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
          </label>
        </header>

        {visibleEntries.length === 0 ? (
          <EmptyState
            compact
            icon={<MessageSquareQuote size={22} />}
            title={keyword.trim() === '' ? '暂无问答条目' : '没有匹配的问答'}
            description={
              keyword.trim() === '' ? '知识库生成完成后，问答条目会显示在这里。' : '换一个关键词试试。'
            }
          />
        ) : (
          <ol className={styles.entryList}>
            {visibleEntries.map((entry, index) => (
              <li key={entry.id} className={styles.entry}>
                <span className={styles.entryIndex}>{index + 1}</span>
                <div className={styles.entryBody}>
                  <h3 className={styles.entryQuestion}>{entry.question}</h3>
                  <p className={styles.entryAnswer}>{entry.answer}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
};

export default KnowledgeDetailPage;
