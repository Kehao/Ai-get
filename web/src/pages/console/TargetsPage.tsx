// 潜客挖掘首页：画像输入、结果数量选择、推荐策略与我的列表。

import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, MoreHorizontal, Sparkles, Upload, User, Users } from 'lucide-react';

import * as targetsApi from '@/api/targets';
import type { TargetList } from '@/api/types';
import Button from '@/components/Button';
import ChipScroller from '@/components/ChipScroller';
import Dropdown from '@/components/Dropdown';
import SegmentedControl from '@/components/SegmentedControl';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { ROUTES } from '@/constants/routes';
import { CATEGORY_LABELS, MINING_PHASE_LABELS } from '@/constants/targets';
import { useAsync } from '@/hooks/useAsync';
import { formatRelativeTime } from '@/utils/format';

import styles from './TargetsPage.module.less';

// 普通挖掘（按条数召回）入口开关：暂以智能发现为唯一主入口，恢复时置回 true
const SHOW_STANDARD_MINING = false;

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

/** 智能发现专用档位。检索源单次硬上限 20 条，候选取材自这批网页，
 *  超过 30 的档位只是心理安慰——所以给智能发现自己的、诚实的小档位。 */
const AGENT_COUNT_OPTIONS = [10, 20, 30];

/** 进行中的列表用阶段名替代笼统的「进行中」，让用户知道卡在哪一步。 */
const phaseLabel = (list: TargetList): string => {
  if (list.status !== 'running') {
    return STATUS_LABELS[list.status];
  }
  return MINING_PHASE_LABELS[list.phase ?? 'searching'] ?? STATUS_LABELS.running;
};

const TargetsPage = (): JSX.Element => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<'company' | 'people'>('company');
  const [query, setQuery] = useState('');
  const [count, setCount] = useState(25);
  // 智能发现与普通挖掘的量级不同（候选来自一批检索网页，约 30 封顶），
  // 所以各有各的档位状态，互不干扰。
  const [agentCount, setAgentCount] = useState(20);
  const [submitting, setSubmitting] = useState(false);
  // 智能发现是一次分钟级的请求，独立加载态：与 submitting 混用会让两个按钮互相锁。
  const [agentRunning, setAgentRunning] = useState(false);

  const overview = useAsync(() => targetsApi.readOverview(), {
    pollIntervalMs: 2500,
    shouldStopPolling: (data) => data !== null && data.running_count === 0,
  });
  // 推荐策略随「找公司 / 找人」切换，deps 必须带上 mode，否则切模式不会重新请求
  const strategies = useAsync(() => targetsApi.readStrategies(mode), { deps: [mode] });
  const countOptions = useAsync(() => targetsApi.readCountOptions());

  const lists = overview.data?.lists ?? [];
  const rowTotal = overview.data?.row_count ?? 0;
  const runningTotal = overview.data?.running_count ?? 0;
  const listTotal = overview.data?.list_count ?? 0;

  const countItems = useMemo(
    () =>
      (countOptions.data ?? []).map((option) => ({
        key: String(option.value),
        label: `${option.value} 条结果`,
      })),
    [countOptions.data],
  );

  const agentCountItems = useMemo(
    () =>
      AGENT_COUNT_OPTIONS.map((value) => ({
        key: String(value),
        label: `${value} 家候选`,
      })),
    [],
  );

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

  const handleAgentDiscover = async (): Promise<void> => {
    const trimmed = query.trim();
    if (trimmed.length < 4) {
      showToast('请至少用一句完整的话描述目标客户画像', 'error');
      return;
    }

    setAgentRunning(true);
    try {
      // 「发现数量」折算成第一步检索条数与提炼轮数：10 → 检索 10 条 + 2 轮，
      // 20/30 → 检索 20 条（源上限）+ 4/6 轮。批次落库后前端逐批显示。
      const created = await targetsApi.agentDiscover(trimmed, agentCount);
      // 接口现在立即返回 running 的空表，结果由后台每批 5 家补进列表——
      // 详情页的轮询会逐批显示，不用在这里等跑完。
      showToast(`智能发现已启动（目标 ${agentCount} 家），结果将逐批显示`, 'success');
      navigate(ROUTES.consoleTargetDetail(created.id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '智能发现失败', 'error');
    } finally {
      setAgentRunning(false);
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
              {/* 普通挖掘入口（结果数量 + 开始挖掘潜客）暂时隐藏：智能发现为主入口。
                  恢复时把 SHOW_STANDARD_MINING 置回 true 即可。 */}
              {SHOW_STANDARD_MINING ? (
                <>
                  <span className={styles.countLabel}>结果数量</span>
                  <Dropdown
                    panelWidth={200}
                    items={countItems}
                    onSelect={(key) => setCount(Number(key))}
                    trigger={({ open }) => (
                      <button type="button" className={[styles.countButton, open ? styles.countButtonOpen : ''].filter(Boolean).join(' ')}>
                        <span>{count}</span>
                        <span className={styles.countUnit}>条</span>
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
                </>
              ) : null}
              <span className={styles.countLabel}>发现数量</span>
              <Dropdown
                panelWidth={200}
                items={agentCountItems}
                onSelect={(key) => setAgentCount(Number(key))}
                trigger={({ open }) => (
                  <button type="button" className={[styles.countButton, open ? styles.countButtonOpen : ''].filter(Boolean).join(' ')}>
                    <span>{agentCount}</span>
                    <span className={styles.countUnit}>家</span>
                  </button>
                )}
              />
              <Button
                variant="primary"
                leadingIcon={<Sparkles size={15} />}
                disabled={query.trim().length < 4 || agentRunning}
                loading={agentRunning}
                onClick={() => void handleAgentDiscover()}
              >
                {/* 等待期＝后端在同步生成评判标准（一次 LLM 调用）；标准一生成完
                    接口就返回并立刻跳列表页，之后的批次在详情页逐批出现。 */}
                {agentRunning ? '生成评判标准…' : '智能发现'}
              </Button>
            </div>
          </div>
        </div>

        <div className={styles.strategyBlock}>
          <span className={styles.strategyLabel}>推荐策略</span>
          <ChipScroller>
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
          </ChipScroller>
        </div>
      </section>

      <section className={styles.listSection}>
        <header className={styles.listHeader}>
          <h2 className={styles.listTitle}>我的列表</h2>
          <div className={styles.listStats}>
            <span className={styles.stat}>
              <strong>{rowTotal}</strong> 条结果
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
                    <Tag tone={STATUS_TONES[list.status]}>{phaseLabel(list)}</Tag>
                    <span className={styles.metaText}>{formatRelativeTime(list.created_at)}</span>
                    <span className={styles.metaText}>
                      <strong>{list.status === 'completed' ? list.requested_count : list.discovered_count}</strong>{' '}
                      {list.mode === 'people' ? '位联系人' : '家公司'}
                    </span>
                    {list.status === 'running' && list.progress_detail ? (
                      <span className={styles.metaText}>
                        已校验 <strong>{list.progress_detail.verified}</strong> / {list.progress_detail.goal}
                      </span>
                    ) : null}
                    {list.source_name ? <span className={styles.metaText}>数据源 {list.source_name}</span> : null}
                  </span>

                  {list.condition_items.length > 0 ? (
                    <span className={styles.listCriteria}>
                      <span className={styles.criteriaLabel}>挖掘标准</span>
                      {list.criteria_label ? (
                        <span
                          className={[styles.criteriaEngine, list.criteria_fallback_reason ? styles.criteriaEngineWarn : '']
                            .filter(Boolean)
                            .join(' ')}
                          title={
                            list.criteria_fallback_reason
                              ? `已降级到规则引擎：${list.criteria_fallback_reason}`
                              : '这批准入标准由它生成'
                          }
                        >
                          {list.criteria_source === 'llm' ? <Sparkles size={11} /> : null}
                          {list.criteria_label}
                        </span>
                      ) : null}
                      {list.condition_items.map((condition) => (
                        <span
                          key={condition.id}
                          className={styles.criteriaChip}
                          title={[CATEGORY_LABELS[condition.category] ?? condition.category, condition.question]
                            .filter((part) => part !== undefined && part !== '')
                            .join(' · ')}
                        >
                          <i className={styles.criteriaBar} style={{ background: condition.color }} />
                          <span className={styles.criteriaText}>{condition.text}</span>
                          {condition.weight > 0 ? <em className={styles.criteriaWeight}>{condition.weight}</em> : null}
                        </span>
                      ))}
                    </span>
                  ) : null}

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
