// 潜客挖掘首页：画像输入、结果数量选择、推荐策略与我的列表。

import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, MoreHorizontal, Sparkles, Upload, User, Users } from 'lucide-react';

import * as targetsApi from '@/api/targets';
import type { TargetList } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import SegmentedControl from '@/components/SegmentedControl';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatRelativeTime } from '@/utils/format';

import styles from './TargetsPage.module.less';

const MODE_OPTIONS = [
  { value: 'company' as const, label: '找公司', icon: <Building2 size={14} /> },
  { value: 'people' as const, label: '找人', icon: <User size={14} /> },
];

const LIST_ACTIONS = [
  { key: 'open', label: '打开列表' },
  { key: 'copy', label: '复制画像描述' },
  { key: 'delete', label: '删除列表', danger: true },
];

const STATUS_TONES = { failed: 'danger', running: 'warning', completed: 'success', pending: 'neutral' } as const;
const STATUS_LABELS = { failed: '失败', running: '进行中', completed: '已完成', pending: '排队中' } as const;

const TargetsPage = (): JSX.Element => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<'company' | 'people'>('company');
  const [query, setQuery] = useState('');
  const [count, setCount] = useState(25);
  const [submitting, setSubmitting] = useState(false);

  const overview = useAsync(() => targetsApi.readOverview(), {
    pollIntervalMs: 2500,
    shouldStopPolling: (data) => data !== null && data.running_count === 0,
  });
  const strategies = useAsync(() => targetsApi.readStrategies());
  const countOptions = useAsync(() => targetsApi.readCountOptions());

  const lists = overview.data?.lists ?? [];
  const companyTotal = overview.data?.company_count ?? 0;
  const runningTotal = overview.data?.running_count ?? 0;
  const listTotal = overview.data?.list_count ?? 0;

  const countItems = useMemo(
    () =>
      (countOptions.data ?? []).map((option) => ({
        key: String(option.value),
        label: `${option.value} 条结果`,
        description: option.is_free ? '免费版可用' : '需要升级套餐',
      })),
    [countOptions.data],
  );

  const selectedOption = (countOptions.data ?? []).find((option) => option.value === count);

  const handleSubmit = async (): Promise<void> => {
    const trimmed = query.trim();
    if (trimmed.length < 4) {
      showToast('请至少用一句完整的话描述目标客户画像', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const created = await targetsApi.createList({ query: trimmed, mode, count });
      showToast('挖掘任务已创建，正在生成潜客列表', 'success');
      navigate(ROUTES.consoleTargetDetail(created.id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '创建挖掘任务失败', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpload = async (file: File): Promise<void> => {
    setSubmitting(true);
    try {
      const result = await targetsApi.uploadList(file);
      showToast(`已导入 ${result.imported_rows} 家公司`, 'success');
      navigate(ROUTES.consoleTargetDetail(result.list_id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '上传失败', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleListAction = async (list: TargetList, key: string): Promise<void> => {
    if (key === 'open') {
      navigate(ROUTES.consoleTargetDetail(list.id));
      return;
    }
    if (key === 'copy') {
      await navigator.clipboard.writeText(list.query);
      showToast('画像描述已复制', 'success');
      return;
    }
    try {
      await targetsApi.deleteList(list.id);
      showToast('列表已删除', 'success');
      overview.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '删除失败', 'error');
    }
  };

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.title}>
          构建完美的<span className={styles.titleAccent}>潜客</span>列表
        </h1>

        <SegmentedControl
          options={MODE_OPTIONS}
          value={mode}
          onChange={setMode}
          size="lg"
          ariaLabel="检索目标"
        />

        <div className={styles.composer}>
          <textarea
            className={styles.textarea}
            placeholder={mode === 'company' ? '描述你的目标客户画像…' : '描述你想找到的联系人画像…'}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <div className={styles.composerFooter}>
            <Button
              variant="outline"
              leadingIcon={<Upload size={15} />}
              onClick={() => fileInputRef.current?.click()}
              disabled={submitting}
            >
              上传客户列表
            </Button>
            <input
              ref={fileInputRef}
              className={styles.fileInput}
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  void handleUpload(file);
                }
                event.target.value = '';
              }}
            />

            <div className={styles.composerActions}>
              <span className={styles.countLabel}>结果数量</span>
              <Dropdown
                panelWidth={200}
                items={countItems}
                onSelect={(key) => setCount(Number(key))}
                trigger={({ open }) => (
                  <button type="button" className={[styles.countButton, open ? styles.countButtonOpen : ''].filter(Boolean).join(' ')}>
                    <span>{count}</span>
                    <span className={styles.countDivider}>·</span>
                    <span>{selectedOption?.is_free ? 'Free' : 'Pro'}</span>
                  </button>
                )}
              />
              <Button
                variant="primary"
                disabled={query.trim().length < 4}
                loading={submitting}
                leadingIcon={<Sparkles size={15} />}
                onClick={() => void handleSubmit()}
              >
                开始挖掘潜客
              </Button>
            </div>
          </div>
        </div>

        <div className={styles.strategyBlock}>
          <span className={styles.strategyLabel}>推荐策略</span>
          <div className={styles.strategyRow}>
            {(strategies.data ?? []).map((strategy) => (
              <button
                key={strategy.id}
                type="button"
                className={styles.strategyChip}
                onClick={() => setQuery(strategy.text)}
              >
                {strategy.text}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.listSection}>
        <header className={styles.listHeader}>
          <h2 className={styles.listTitle}>我的列表</h2>
          <div className={styles.listStats}>
            <span className={styles.stat}>
              <strong>{companyTotal}</strong> 条结果
            </span>
            <span className={styles.stat}>
              <strong>{runningTotal}</strong> 进行中
            </span>
            <span className={styles.stat}>
              <strong>{listTotal}</strong> 个列表
            </span>
          </div>
        </header>

        {lists.length === 0 ? (
          <div className={styles.listEmpty}>
            <Users size={22} />
            <p>还没有潜客列表，先用一句话描述你的目标客户画像吧。</p>
          </div>
        ) : (
          <div className={styles.listGrid}>
            {lists.map((list) => (
              <article key={list.id} className={styles.listCard}>
                <button
                  type="button"
                  className={styles.listCardBody}
                  onClick={() => navigate(ROUTES.consoleTargetDetail(list.id))}
                >
                  <span className={styles.listQuery}>{list.query}</span>
                  <span className={styles.listMeta}>
                    <Tag tone={STATUS_TONES[list.status]}>{STATUS_LABELS[list.status]}</Tag>
                    <span className={styles.metaText}>{formatRelativeTime(list.created_at)}</span>
                    <span className={styles.metaText}>
                      <strong>{list.status === 'completed' ? list.requested_count : list.discovered_count}</strong> 家公司
                    </span>
                  </span>
                  <span className={styles.listPlan}>{list.follow_up_plan ?? '暂无跟进计划'}</span>
                </button>

                <div className={styles.listActions}>
                  <Dropdown
                    items={LIST_ACTIONS}
                    onSelect={(key) => void handleListAction(list, key)}
                    panelWidth={168}
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
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default TargetsPage;
