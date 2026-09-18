// 企业背调详情：调研报告与调研过程对话。

import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2, Trash2, Wrench } from 'lucide-react';

import * as researchApi from '@/api/research';
import Button from '@/components/Button';
import EmptyState from '@/components/EmptyState';
import Markdown from '@/components/Markdown';
import ProgressBar from '@/components/ProgressBar';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTime } from '@/utils/format';

import styles from './ResearchDetailPage.module.less';

const STATUS_TONES = { failed: 'danger', running: 'warning', completed: 'success', pending: 'neutral' } as const;
const STATUS_LABELS = { failed: '失败', running: '进行中', completed: '已完成', pending: '排队中' } as const;

const ResearchDetailPage = (): JSX.Element => {
  const { recordId = '' } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const detail = useAsync(() => researchApi.readRecord(recordId), {
    pollIntervalMs: 2000,
    shouldStopPolling: (data) => data !== null && data.record.status !== 'running',
    deps: [recordId],
  });

  const record = detail.data?.record;
  const messages = detail.data?.messages ?? [];
  const running = record?.status === 'running';

  const handleDelete = async (): Promise<void> => {
    if (record === undefined) {
      return;
    }
    try {
      await researchApi.deleteRecord(record.id);
      showToast('调研记录已删除', 'success');
      navigate(ROUTES.consoleResearch, { replace: true });
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  if (detail.loading && record === undefined) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在加载调研报告…</span>
      </div>
    );
  }

  if (detail.error !== null && record === undefined) {
    return (
      <EmptyState
        title="调研记录不可用"
        description={detail.error}
        action={
          <Link to={ROUTES.consoleResearch}>
            <Button variant="outline">返回企业背调</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <Link to={ROUTES.consoleResearch} className={styles.back}>
            <ArrowLeft size={15} />
            企业背调
          </Link>

          <Button
            variant="ghost"
            size="sm"
            leadingIcon={<Trash2 size={14} />}
            onClick={() => void handleDelete()}
          >
            删除记录
          </Button>
        </div>

        <h1 className={styles.title}>{record?.title ?? record?.query}</h1>

        <div className={styles.headerMeta}>
          <Tag tone={STATUS_TONES[record?.status ?? 'pending']}>{STATUS_LABELS[record?.status ?? 'pending']}</Tag>
          <span className={styles.metaText}>
            <strong>{record?.card_count ?? 0}</strong> 数据卡片
          </span>
          <span className={styles.metaText}>
            <strong>{record?.conversation_turns ?? 0}</strong> 轮对话
          </span>
          <span className={styles.metaText}>
            <strong>{record?.tool_calls ?? 0}</strong> 工具调用
          </span>
          {record ? <span className={styles.metaText}>更新于 {formatDateTime(record.updated_at)}</span> : null}
        </div>

        {running ? (
          <div className={styles.progress}>
            <ProgressBar value={record?.progress ?? 0} showLabel label="调研进度" />
          </div>
        ) : null}
      </header>

      <div className={styles.body}>
        <article className={styles.reportCard}>
          <h2 className={styles.sectionTitle}>调研报告</h2>
          {running ? (
            <div className={styles.reportPending}>
              <Loader2 size={18} className={styles.spin} />
              <span>智能体正在检索公开信息并撰写报告…</span>
            </div>
          ) : (
            <div className={styles.reportContent}>
              <Markdown source={record?.report_markdown ?? ''} />
            </div>
          )}
        </article>

        <aside className={styles.conversation}>
          <h2 className={styles.sectionTitle}>调研过程</h2>

          {messages.length === 0 ? (
            <p className={styles.conversationEmpty}>暂无对话记录。</p>
          ) : (
            <ul className={styles.messageList}>
              {messages.map((message) => (
                <li
                  key={message.id}
                  className={[styles.message, message.role === 'user' ? styles.messageUser : styles.messageAssistant]
                    .filter(Boolean)
                    .join(' ')}
                >
                  <span className={styles.messageRole}>{message.role === 'user' ? '你' : 'Ai-get 智能体'}</span>
                  <p className={styles.messageText}>{message.content}</p>
                  {message.tool_name !== null ? (
                    <span className={styles.toolCall}>
                      <Wrench size={12} />
                      {message.tool_name}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
};

export default ResearchDetailPage;
