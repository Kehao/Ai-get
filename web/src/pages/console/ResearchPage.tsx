// 企业背调首页：调研输入、推荐问题与调研记录。

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, FileText, MoreHorizontal, Paperclip, Sparkles } from 'lucide-react';

import * as researchApi from '@/api/research';
import type { ResearchRecord } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatDateTime, truncate } from '@/utils/format';

import styles from './ResearchPage.module.less';

const STATUS_TONES = { failed: 'danger', running: 'warning', completed: 'success', pending: 'neutral' } as const;
const STATUS_LABELS = { failed: '失败', running: '进行中', completed: '已完成', pending: '排队中' } as const;

const RECORD_ACTIONS = [
  { key: 'open', label: '查看报告' },
  { key: 'copy', label: '复制调研问题' },
  { key: 'delete', label: '删除记录', danger: true },
];

/** 报告摘要：把 Markdown 折叠成单行文本，用于卡片上的预览。 */
const toReportExcerpt = (markdown: string): string =>
  truncate(markdown.replace(/[#*>`\-\n]+/g, ' ').replace(/\s+/g, ' ').trim(), 180);

const ResearchPage = (): JSX.Element => {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [query, setQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const records = useAsync(() => researchApi.readRecords(), {
    pollIntervalMs: 2500,
    shouldStopPolling: (data) => data !== null && data.running_count === 0,
  });
  const questions = useAsync(() => researchApi.readQuestions());

  const items = records.data?.records ?? [];

  const handleSubmit = async (): Promise<void> => {
    const trimmed = query.trim();
    if (trimmed.length < 4) {
      showToast('请输入公司名或官网，至少一句完整描述', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const created = await researchApi.createRecord(trimmed);
      setQuery('');
      showToast('已开始背调，正在生成调研报告', 'success');
      navigate(ROUTES.consoleResearchDetail(created.id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '创建调研任务失败', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAction = async (record: ResearchRecord, key: string): Promise<void> => {
    if (key === 'open') {
      navigate(ROUTES.consoleResearchDetail(record.id));
      return;
    }
    if (key === 'copy') {
      await navigator.clipboard.writeText(record.query);
      showToast('调研问题已复制', 'success');
      return;
    }
    try {
      await researchApi.deleteRecord(record.id);
      showToast('调研记录已删除', 'success');
      records.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.title}>目标客户深度研究</h1>
        <p className={styles.subtitle}>输入公司名或官网，全景洞察企业经营、组织架构及真实采购习惯。</p>

        <div className={styles.composer}>
          <textarea
            className={styles.textarea}
            placeholder="帮我调研 Fashion Nova 这家公司"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <div className={styles.composerFooter}>
            <button
              type="button"
              className={styles.attachButton}
              disabled
              title="附件能力暂未开放"
              aria-label="附件能力暂未开放"
            >
              <Paperclip size={16} />
            </button>

            <Button
              variant="primary"
              size="lg"
              disabled={query.trim().length < 4}
              loading={submitting}
              onClick={() => void handleSubmit()}
            >
              开始背调
              <ArrowRight size={15} />
            </Button>
          </div>
        </div>

        <div className={styles.questionBlock}>
          <span className={styles.questionLabel}>推荐问题</span>
          <div className={styles.questionRow}>
            {(questions.data ?? []).map((question) => (
              <button
                key={question}
                type="button"
                className={styles.questionChip}
                onClick={() => setQuery(question)}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.recordSection}>
        <header className={styles.recordHeader}>
          <h2 className={styles.recordTitle}>调研记录</h2>
          <div className={styles.recordStats}>
            <span className={styles.stat}>
              <strong>{records.data?.report_count ?? 0}</strong> 份报告
            </span>
            <span className={styles.stat}>
              <strong>{records.data?.running_count ?? 0}</strong> 进行中
            </span>
            <span className={styles.stat}>
              <strong>{items.length}</strong> 条记录
            </span>
          </div>
        </header>

        {items.length === 0 ? (
          <div className={styles.recordEmpty}>
            <FileText size={22} />
            <p>还没有调研记录，输入公司名开始第一次企业背调吧。</p>
          </div>
        ) : (
          <div className={styles.recordGrid}>
            {items.map((record) => (
              <article key={record.id} className={styles.recordCard}>
                <div className={styles.recordTop}>
                  <button
                    type="button"
                    className={styles.recordHeading}
                    onClick={() => navigate(ROUTES.consoleResearchDetail(record.id))}
                  >
                    <h3 className={styles.recordName}>{record.title}</h3>
                    <span className={styles.recordMeta}>
                      <Tag tone={STATUS_TONES[record.status]}>{STATUS_LABELS[record.status]}</Tag>
                      <span className={styles.metaText}>
                        <strong>{record.card_count}</strong> 数据卡片
                      </span>
                    </span>
                  </button>

                  <Dropdown
                    items={RECORD_ACTIONS}
                    panelWidth={168}
                    onSelect={(key) => void handleAction(record, key)}
                    trigger={({ open }) => (
                      <button
                        type="button"
                        className={[styles.moreButton, open ? styles.moreButtonOpen : ''].filter(Boolean).join(' ')}
                        aria-label="更多操作"
                      >
                        <MoreHorizontal size={16} />
                      </button>
                    )}
                  />
                </div>

                <p className={styles.recordExcerpt}>{toReportExcerpt(record.report_markdown)}</p>

                <footer className={styles.recordFooter}>
                  <span className={styles.footerText}>更新于 {formatDateTime(record.updated_at)}</span>
                  <span className={styles.footerText}>
                    <strong>{record.conversation_turns}</strong> 轮对话
                  </span>
                  <span className={styles.footerText}>
                    <strong>{record.tool_calls}</strong> 工具调用
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    leadingIcon={<Sparkles size={14} />}
                    onClick={() => navigate(ROUTES.consoleResearchDetail(record.id))}
                  >
                    查看
                  </Button>
                </footer>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default ResearchPage;
