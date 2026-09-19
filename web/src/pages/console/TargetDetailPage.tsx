// 潜客列表详情：数据表格 + 右侧「挖掘 / 详情」双面板。
// 挖掘面板负责编辑寻找对象与判断条件、解释挖掘策略、查看并追加进度；
// 点击表格任意一行后切到详情面板，展示该企业的完整档案与准入条件评估。

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpDown,
  Filter,
  Globe,
  Info,
  Link2,
  ListChecks,
  MoreHorizontal,
  PanelRight,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  TrendingUp,
  UserPlus,
  X,
} from 'lucide-react';

import * as agentsApi from '@/api/agents';
import * as targetsApi from '@/api/targets';
import type { Contact, TargetCompany, TargetCondition, TargetList } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import Modal from '@/components/Modal';
import Pagination from '@/components/Pagination';
import Spinner from '@/components/Spinner';
import Tag, { type TagTone } from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { CONDITION_COLORS } from '@/constants/targets';
import { OUTREACH_CHANNELS } from '@/constants/channels';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatFullDateTime, formatNumber, toDisplayDomain, toDomainInitial } from '@/utils/format';

import styles from './TargetDetailPage.module.less';

const PAGE_SIZE = 20;
const MORE_OPTIONS = [25, 100, 500, 1000];
const MATCH_TONES: Record<string, TagTone> = {
  明确符合: 'success',
  可能符合: 'warning',
  待确认: 'neutral',
};
const EVAL_TONES: Record<string, string> = {
  符合: 'evalMatch',
  不确定: 'evalUnsure',
  不符合: 'evalMiss',
};
const FILTER_OPTIONS = [
  { key: '', label: '全部结论' },
  { key: '明确符合', label: '明确符合' },
  { key: '可能符合', label: '可能符合' },
  { key: '待确认', label: '待确认' },
];
const SORT_OPTIONS = [
  { key: 'match', label: '按相关度' },
  { key: 'name', label: '按公司名' },
  { key: 'website', label: '按网址' },
];

/** 本地新增的条件行需要一个临时 id，保存后由后端重新编号。 */
const DRAFT_CONDITION_PREFIX = 'draft-condition';

const TargetDetailPage = (): JSX.Element => {
  const { listId = '' } = useParams();
  const { showToast } = useToast();

  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [matchLevel, setMatchLevel] = useState('');
  const [sort, setSort] = useState('match');

  const [panelTab, setPanelTab] = useState<'mining' | 'detail'>('mining');
  const [panelOpen, setPanelOpen] = useState(true);
  const [activeRowId, setActiveRowId] = useState('');
  const [evidenceTitle, setEvidenceTitle] = useState('');
  const [evidenceItems, setEvidenceItems] = useState<string[]>([]);
  const [moreCount, setMoreCount] = useState(MORE_OPTIONS[0]);

  // 草稿为 null 时表示「跟随服务端数据」，保存成功后重置回 null 即可还原为未编辑状态
  const [draftQuery, setDraftQuery] = useState<string | null>(null);
  const [draftConditions, setDraftConditions] = useState<TargetCondition[] | null>(null);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [contactsRow, setContactsRow] = useState<TargetCompany | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [outreachOpen, setOutreachOpen] = useState(false);
  const [columnOpen, setColumnOpen] = useState(false);
  const [columnName, setColumnName] = useState('');
  const [channel, setChannel] = useState(OUTREACH_CHANNELS[0]);
  const [agentName, setAgentName] = useState('');
  const [busy, setBusy] = useState(false);

  const detail = useAsync(
    () => targetsApi.readListDetail(listId, { page, page_size: PAGE_SIZE, keyword, match_level: matchLevel, sort }),
    {
      pollIntervalMs: 2500,
      shouldStopPolling: (data) => data !== null && data.target_list.status === 'completed',
      deps: [listId, page, keyword, matchLevel, sort],
    },
  );
  const agents = useAsync(() => agentsApi.readAgents());
  const companyDetail = useAsync(
    () => (activeRowId === '' ? Promise.resolve(null) : targetsApi.readCompanyDetail(listId, activeRowId)),
    { deps: [listId, activeRowId] },
  );

  // 查询参数变化后清空选择，避免选中项与当前页数据不一致
  useEffect(() => setSelectedIds([]), [listId, page, keyword, matchLevel, sort]);

  const targetList: TargetList | null = detail.data?.target_list ?? null;
  const columns = detail.data?.columns ?? [];
  const rows = detail.data?.companies.items ?? [];
  const total = detail.data?.companies.total ?? 0;
  const customColumns = useMemo(() => columns.filter((column) => !column.is_builtin), [columns]);

  const agentOptions = useMemo(() => agents.data ?? [], [agents.data]);
  const defaultAgentName = agentOptions[0]?.name ?? 'REVOR 默认销售智能体';

  useEffect(() => {
    setAgentName((current) => current || defaultAgentName);
  }, [defaultAgentName]);

  const serverConditions = useMemo(() => targetList?.condition_items ?? [], [targetList]);
  const conditions = draftConditions ?? serverConditions;
  const queryText = draftQuery ?? targetList?.query ?? '';
  const strategyGroups = targetList?.strategy_groups ?? [];
  const configDirty =
    targetList !== null &&
    (queryText.trim() !== targetList.query ||
      conditions.map((item) => item.text.trim()).join('|') !==
        serverConditions.map((item) => item.text.trim()).join('|'));

  const openContacts = async (row: TargetCompany): Promise<void> => {
    setContactsRow(row);
    setContacts([]);
    setContactsLoading(true);
    try {
      setContacts(await targetsApi.readContacts(listId, row.id));
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '获取联系人失败', 'error');
    } finally {
      setContactsLoading(false);
    }
  };

  const retryField = async (row: TargetCompany, field: 'summary' | 'contacts' | 'official_contact'): Promise<void> => {
    try {
      await targetsApi.retryField(listId, row.id, field);
      showToast('已重新富化该字段', 'success');
      detail.reload();
      companyDetail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '重新富化失败', 'error');
    }
  };

  const selectRow = (rowId: string): void => {
    setActiveRowId(rowId);
    setPanelTab('detail');
    setPanelOpen(true);
  };

  const resetDrafts = (): void => {
    setDraftQuery(null);
    setDraftConditions(null);
  };

  const updateConditionText = (conditionId: string, text: string): void => {
    setDraftConditions(conditions.map((item) => (item.id === conditionId ? { ...item, text } : item)));
  };

  const addCondition = (): void => {
    setDraftConditions([
      ...conditions,
      {
        id: `${DRAFT_CONDITION_PREFIX}-${conditions.length}-${Date.now()}`,
        text: '',
        color: CONDITION_COLORS[conditions.length % CONDITION_COLORS.length],
      },
    ]);
  };

  const removeCondition = (conditionId: string): void => {
    setDraftConditions(conditions.filter((item) => item.id !== conditionId));
  };

  /** 保存配置与开始挖掘共用：先落库再决定是否重跑。 */
  const persistConfig = async (): Promise<boolean> => {
    const texts = conditions.map((item) => item.text.trim()).filter((text) => text !== '');
    if (texts.length === 0) {
      showToast('至少需要保留一条判断条件', 'error');
      return false;
    }
    await targetsApi.updateConditions(listId, { query: queryText, conditions: texts });
    resetDrafts();
    return true;
  };

  const saveConfig = async (): Promise<void> => {
    setBusy(true);
    try {
      if (await persistConfig()) {
        showToast('挖掘配置已保存', 'success');
        detail.reload();
      }
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '保存配置失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const startMining = async (): Promise<void> => {
    setBusy(true);
    try {
      if (!(await persistConfig())) {
        return;
      }
      await targetsApi.remine(listId);
      setActiveRowId('');
      setPanelTab('mining');
      showToast('已按最新配置重新开始挖掘', 'success');
      detail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '重新挖掘失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const addColumn = async (): Promise<void> => {
    const name = columnName.trim();
    if (name.length < 2) {
      showToast('请描述要挖掘的字段，例如「是否已上线微信小程序」', 'error');
      return;
    }
    setBusy(true);
    try {
      await targetsApi.addColumn(listId, name);
      showToast(`已新增调研列：${name}`, 'success');
      setColumnOpen(false);
      setColumnName('');
      detail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '新增调研列失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const submitOutreach = async (): Promise<void> => {
    setBusy(true);
    try {
      const plan = await targetsApi.createOutreach(listId, agentName, channel);
      showToast(`智能触达计划已创建，共 ${plan.steps.length} 个触点`, 'success');
      setOutreachOpen(false);
      detail.reload();
      companyDetail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '创建触达计划失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const addMore = async (count: number): Promise<void> => {
    setBusy(true);
    try {
      await targetsApi.addMoreCompanies(listId, count);
      showToast(`已追加 ${count} 家企业`, 'success');
      detail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '追加失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const exportCsv = (): void => {
    const header = ['所属公司', '网址', '行业', 'AI 摘要', '综合结果', '联系人数'];
    const lines = rows.map((row) =>
      [row.company_name, row.website, row.industries.join(' / '), row.ai_summary.replace(/\n/g, ' '), row.match_level, String(row.contact_count)]
        .map((cell) => `"${cell.replace(/"/g, '""')}"`)
        .join(','),
    );
    const blob = new Blob([`\uFEFF${[header.join(','), ...lines].join('\n')}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ai-get-潜客列表-${targetList?.id ?? 'export'}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('已导出当前页数据', 'success');
  };

  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.includes(row.id));

  const toggleAll = (): void => {
    setSelectedIds(allSelected ? [] : rows.map((row) => row.id));
  };

  const toggleRow = (rowId: string): void => {
    setSelectedIds((current) => (current.includes(rowId) ? current.filter((id) => id !== rowId) : [...current, rowId]));
  };

  if (detail.error) {
    return (
      <div className={styles.state}>
        <p>{detail.error}</p>
        <Link to={ROUTES.consoleTargets}>返回潜客挖掘</Link>
      </div>
    );
  }

  if (targetList === null) {
    return (
      <div className={styles.state}>
        <Spinner size={20} />
        <span>正在读取列表…</span>
      </div>
    );
  }

  const running = targetList.status === 'running';
  const dossier = companyDetail.data;

  return (
    <div className={styles.page}>
      <header className={styles.toolbar}>
        <Link className={styles.back} to={ROUTES.consoleTargets} aria-label="返回潜客挖掘">
          <ArrowLeft size={16} />
        </Link>

        <div className={styles.toolbarTitle}>
          <p className={styles.toolbarQuery}>{targetList.query}</p>
          <div className={styles.toolbarMeta}>
            <Tag tone={running ? 'warning' : 'success'}>{running ? '进行中' : '已完成'}</Tag>
            <span>{formatNumber(targetList.discovered_count)} / {formatNumber(targetList.requested_count)} 家</span>
            <span>已获取联系人 {formatNumber(targetList.contact_count)} 位</span>
          </div>
        </div>

        <div className={styles.toolbarActions}>
          <Dropdown
            align="end"
            panelWidth={168}
            items={FILTER_OPTIONS}
            onSelect={(key) => {
              setMatchLevel(key);
              setPage(1);
            }}
            trigger={({ open }) => (
              <button type="button" className={[styles.toolButton, open ? styles.toolButtonOpen : ''].filter(Boolean).join(' ')}>
                <Filter size={15} />
                筛选
              </button>
            )}
          />
          <Dropdown
            align="end"
            panelWidth={168}
            items={SORT_OPTIONS}
            onSelect={(key) => {
              setSort(key);
              setPage(1);
            }}
            trigger={({ open }) => (
              <button type="button" className={[styles.toolButton, open ? styles.toolButtonOpen : ''].filter(Boolean).join(' ')}>
                <ArrowUpDown size={15} />
                排序
              </button>
            )}
          />
          <Dropdown
            align="end"
            panelWidth={180}
            items={[
              { key: 'refresh', label: '刷新数据' },
              { key: 'export', label: '导出当前页 CSV' },
            ]}
            onSelect={(key) => (key === 'export' ? exportCsv() : detail.reload())}
            trigger={({ open }) => (
              <button type="button" className={[styles.toolButton, open ? styles.toolButtonOpen : ''].filter(Boolean).join(' ')}>
                <MoreHorizontal size={15} />
                更多
              </button>
            )}
          />

          <Button
            variant="outline"
            leadingIcon={<Send size={15} />}
            onClick={() => setOutreachOpen(true)}
            disabled={selectedIds.length === 0 && rows.length === 0}
          >
            智能触达
          </Button>
          <Button variant="primary" leadingIcon={<UserPlus size={15} />} onClick={() => setColumnOpen(true)}>
            添加智能调研
          </Button>
        </div>
      </header>

      <div className={styles.body}>
        <section className={styles.tableArea}>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.checkCell}>
                    <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="全选当前页" />
                  </th>
                  <th className={styles.indexCell} aria-label="序号" />
                  <th>所属公司</th>
                  <th>网址</th>
                  <th>行业</th>
                  <th className={styles.summaryCell}>AI 摘要</th>
                  <th>综合结果</th>
                  <th>企业关键联系人挖掘</th>
                  <th>官网联系方式挖掘</th>
                  {customColumns.map((column) => (
                    <th key={column.id}>{column.name}</th>
                  ))}
                  <th className={styles.actionCell}>
                    <button type="button" className={styles.addColumn} onClick={() => setColumnOpen(true)}>
                      <Sparkles size={14} />
                      添加智能调研
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={row.id}
                    className={[styles.row, row.id === activeRowId ? styles.rowActive : ''].filter(Boolean).join(' ')}
                    onClick={() => selectRow(row.id)}
                  >
                    <td className={styles.checkCell} onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(row.id)}
                        onChange={() => toggleRow(row.id)}
                        aria-label={`选择 ${row.company_name}`}
                      />
                    </td>
                    <td className={styles.indexCell}>{(page - 1) * PAGE_SIZE + index + 1}</td>
                    <td>
                      <div className={styles.companyCell}>
                        <span className={styles.companyMark}>{toDomainInitial(row.website)}</span>
                        <div className={styles.companyText}>
                          <strong>{row.company_name}</strong>
                          <small>{row.location} · {row.employees} · {row.funding_stage}</small>
                        </div>
                      </div>
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <a
                        className={styles.website}
                        href={`https://${toDisplayDomain(row.website)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Globe size={12} />
                        {toDisplayDomain(row.website)}
                      </a>
                    </td>
                    <td>
                      <div className={styles.industryList}>
                        {row.industries.map((industry) => (
                          <Tag key={industry} tone="neutral">
                            {industry}
                          </Tag>
                        ))}
                      </div>
                    </td>
                    <td className={styles.summaryCell}>
                      {row.summary_state === 'ready' ? (
                        <p className={styles.summaryText}>{row.ai_summary}</p>
                      ) : (
                        <button
                          type="button"
                          className={styles.retryButton}
                          onClick={(event) => {
                            event.stopPropagation();
                            void retryField(row, 'summary');
                          }}
                        >
                          <RefreshCw size={13} />
                          重试生成摘要
                        </button>
                      )}
                    </td>
                    <td>
                      <Tag tone={MATCH_TONES[row.match_level] ?? 'neutral'}>{row.match_level}</Tag>
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      {row.contact_state === 'ready' ? (
                        <button type="button" className={styles.contactButton} onClick={() => void openContacts(row)}>
                          {row.contact_count} 人
                        </button>
                      ) : (
                        <button type="button" className={styles.retryButton} onClick={() => void retryField(row, 'contacts')}>
                          <RefreshCw size={13} />
                          重试该字段
                        </button>
                      )}
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      {row.official_contact_state === 'blocked' ? (
                        <button
                          type="button"
                          className={styles.retryButton}
                          onClick={() => void retryField(row, 'official_contact')}
                        >
                          <RefreshCw size={13} />
                          官网访问受限
                        </button>
                      ) : (
                        <span className={styles.muted}>已获取</span>
                      )}
                    </td>
                    {customColumns.map((column) => (
                      <td key={column.id}>
                        <span className={styles.customValue}>{row.custom_values[column.id] ?? '—'}</span>
                      </td>
                    ))}
                    <td className={styles.actionCell}>
                      <button
                        type="button"
                        className={styles.rowAction}
                        aria-label={`查看 ${row.company_name} 详情`}
                        onClick={(event) => {
                          event.stopPropagation();
                          selectRow(row.id);
                        }}
                      >
                        <Info size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {rows.length === 0 && !detail.loading ? (
            <div className={styles.emptyRows}>
              {running ? '正在挖掘中，稍后会陆续出现结果…' : '没有符合当前筛选条件的企业'}
            </div>
          ) : null}

          <footer className={styles.tableFooter}>
            <input
              className={styles.search}
              placeholder="搜索公司名、行业或摘要…"
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value);
                setPage(1);
              }}
            />
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
          </footer>
        </section>

        <aside className={[styles.panel, panelOpen ? '' : styles.panelCollapsed].filter(Boolean).join(' ')}>
          {panelOpen ? (
            <>
              <div className={styles.panelTabs}>
                <div className={styles.tabGroup}>
                  <button
                    type="button"
                    className={panelTab === 'mining' ? styles.panelTabActive : styles.panelTab}
                    onClick={() => setPanelTab('mining')}
                  >
                    挖掘
                  </button>
                  <button
                    type="button"
                    className={panelTab === 'detail' ? styles.panelTabActive : styles.panelTab}
                    onClick={() => setPanelTab('detail')}
                  >
                    详情
                  </button>
                </div>
                <button
                  type="button"
                  className={styles.panelToggle}
                  onClick={() => setPanelOpen(false)}
                  aria-label="收起右侧面板"
                >
                  <PanelRight size={15} />
                </button>
              </div>

              {panelTab === 'mining' ? (
                <div className={styles.panelBody}>
                  <section className={styles.card}>
                    <header className={styles.cardHeader}>
                      <span className={styles.cardIcon}>
                        <ListChecks size={14} />
                      </span>
                      <h3 className={styles.cardTitle}>条件</h3>
                      <span className={styles.cardHint}>寻找对象</span>
                    </header>

                    <textarea
                      className={styles.queryInput}
                      value={queryText}
                      rows={3}
                      placeholder="用一段话描述你要找的企业，例如：杭州的消费品与旅游行业小微商家…"
                      onChange={(event) => setDraftQuery(event.target.value)}
                    />

                    <div className={styles.conditionList}>
                      {conditions.map((condition) => (
                        <div key={condition.id} className={styles.conditionRow}>
                          <span className={styles.conditionBar} style={{ background: condition.color }} />
                          <input
                            className={styles.conditionInput}
                            value={condition.text}
                            placeholder="输入判断条件"
                            onChange={(event) => updateConditionText(condition.id, event.target.value)}
                          />
                          <button
                            type="button"
                            className={styles.conditionRemove}
                            onClick={() => removeCondition(condition.id)}
                            aria-label={`删除条件：${condition.text || '未填写'}`}
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className={styles.conditionActions}>
                      <button type="button" className={styles.textButton} onClick={addCondition}>
                        <Plus size={12} />
                        增加判断条件
                      </button>
                      <button type="button" className={styles.textButtonMuted} disabled title="排除名单暂未开放">
                        排除名单
                      </button>
                      <button
                        type="button"
                        className={styles.saveButton}
                        disabled={!configDirty || busy}
                        onClick={() => void saveConfig()}
                      >
                        保存配置
                      </button>
                    </div>

                    <button
                      type="button"
                      className={styles.mineButton}
                      disabled={!configDirty || busy}
                      title={configDirty ? undefined : '配置未改动，先调整寻找对象或判断条件'}
                      onClick={() => void startMining()}
                    >
                      <Search size={15} />
                      开始挖掘
                    </button>
                    {configDirty ? null : (
                      <p className={styles.configHint}>当前配置与已保存的一致，改动后即可重新挖掘。</p>
                    )}
                  </section>

                  {strategyGroups.length > 0 ? (
                    <section className={styles.card}>
                      <header className={styles.cardHeader}>
                        <span className={styles.cardIcon}>
                          <Search size={14} />
                        </span>
                        <h3 className={styles.cardTitle}>挖掘策略</h3>
                        <span className={styles.cardBadge}>{strategyGroups.length}组</span>
                      </header>

                      <div className={styles.strategyList}>
                        {strategyGroups.map((group) => (
                          <article key={group.id} className={styles.strategyGroup}>
                            <h4 className={styles.strategyTitle}>
                              <span className={styles.strategyDot} />
                              {group.title}
                            </h4>
                            <p className={styles.strategyDesc}>{group.description}</p>
                            <ul className={styles.strategyExamples}>
                              {group.examples.map((example) => (
                                <li key={example}>
                                  <Search size={11} />
                                  {example}
                                </li>
                              ))}
                            </ul>
                          </article>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  <section className={[styles.card, styles.progressCard].filter(Boolean).join(' ')}>
                    <header className={styles.cardHeader}>
                      <span className={styles.cardIcon}>
                        <TrendingUp size={14} />
                      </span>
                      <h3 className={styles.cardTitle}>挖掘进度</h3>
                      <span className={styles.progressValue}>
                        <strong>{formatNumber(targetList.discovered_count)}</strong>
                        <i>/</i>
                        {formatNumber(targetList.requested_count)}
                      </span>
                    </header>

                    <div className={styles.progressTrack}>
                      <div className={styles.progressFill} style={{ width: `${targetList.progress}%` }} />
                    </div>
                    <p className={styles.progressHint}>
                      {running ? '正在实时检索匹配企业并富化字段…' : '本轮挖掘已完成，可继续追加更多结果。'}
                    </p>

                    <div className={styles.moreButtons}>
                      {MORE_OPTIONS.map((value) => (
                        <button
                          key={value}
                          type="button"
                          className={value === moreCount ? styles.moreChipActive : styles.moreChip}
                          onClick={() => setMoreCount(value)}
                        >
                          {value}
                        </button>
                      ))}
                    </div>

                    <button
                      type="button"
                      className={styles.moreButton}
                      disabled={busy}
                      onClick={() => void addMore(moreCount)}
                    >
                      挖掘更多
                    </button>
                  </section>
                </div>
              ) : (
                <div className={styles.panelBody}>
                  {activeRowId === '' ? (
                    <p className={styles.dossierEmpty}>点击左侧任意一行企业，查看它的详细档案与准入条件评估。</p>
                  ) : companyDetail.loading && dossier === null ? (
                    <div className={styles.dossierLoading}>
                      <Spinner size={18} />
                      <span>正在读取详细档案…</span>
                    </div>
                  ) : dossier === null ? (
                    <p className={styles.dossierEmpty}>{companyDetail.error ?? '未能读取该企业的详细档案。'}</p>
                  ) : (
                    <div className={styles.dossier}>
                      <header className={styles.dossierHead}>
                        <span className={styles.dossierLabel}>详细档案</span>
                        <h3 className={styles.dossierName}>{dossier.company.company_name}</h3>
                        <span className={styles.dossierBadge}>company</span>
                        <a
                          className={styles.dossierLink}
                          href={`https://${toDisplayDomain(dossier.company.website)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Link2 size={11} />
                          {toDisplayDomain(dossier.company.website)}
                        </a>
                      </header>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>AI 摘要</span>
                        <p className={styles.blockText}>
                          {dossier.company.ai_summary || '摘要尚未生成，可在表格中对该字段发起重新富化。'}
                        </p>
                      </section>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>智能触达</span>
                        <p className={styles.blockText}>{dossier.outreach_note}</p>
                        {dossier.outreach === null ? null : (
                          <p className={styles.blockMeta}>
                            {dossier.outreach.agent_name} · {dossier.outreach.channel} ·{' '}
                            {dossier.outreach.steps.length} 个触点
                          </p>
                        )}
                      </section>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>References · {dossier.references.length}</span>
                        <ul className={styles.referenceList}>
                          {dossier.references.map((item) => (
                            <li key={item.url}>
                              <span className={styles.referenceTitle}>{item.title}</span>
                              <a className={styles.referenceLink} href={item.url} target="_blank" rel="noreferrer">
                                <Link2 size={10} />
                                {toDisplayDomain(item.url)}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </section>

                      <dl className={styles.infoBlock}>
                        <div>
                          <dt>名称</dt>
                          <dd>{dossier.company.company_name}</dd>
                        </div>
                        <div>
                          <dt>行业</dt>
                          <dd>{dossier.company.industries.join('、')}</dd>
                        </div>
                        <div>
                          <dt>地区</dt>
                          <dd>{dossier.company.location}</dd>
                        </div>
                        <div>
                          <dt>规模</dt>
                          <dd>{dossier.company.employees} · {dossier.company.funding_stage}</dd>
                        </div>
                        <div>
                          <dt>创建时间</dt>
                          <dd>{formatFullDateTime(dossier.company.created_at)}</dd>
                        </div>
                      </dl>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>智能调研</span>
                        <ul className={styles.researchList}>
                          {dossier.research_results.map((result) => (
                            <li key={result.key} className={styles.researchItem}>
                              <strong className={styles.researchTitle}>{result.title}</strong>
                              <span
                                className={
                                  result.state === 'ready' ? styles.researchSummaryReady : styles.researchSummaryEmpty
                                }
                              >
                                {result.summary}
                              </span>
                              <button
                                type="button"
                                className={styles.evidenceButton}
                                onClick={() => {
                                  setEvidenceTitle(result.title);
                                  setEvidenceItems(result.evidence);
                                }}
                              >
                                查看依据
                              </button>
                            </li>
                          ))}
                        </ul>
                      </section>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>准入条件评估</span>
                        <ul className={styles.evalList}>
                          {dossier.evaluations.map((item) => (
                            <li key={item.condition} className={styles.evalItem}>
                              <div className={styles.evalHead}>
                                <strong className={styles.evalCondition}>{item.condition}</strong>
                                <span className={styles[EVAL_TONES[item.status] ?? 'evalUnsure']}>{item.status}</span>
                                <span className={styles.evalRef}>参考 {item.reference_count}</span>
                              </div>
                              <p className={styles.evalText}>{item.explanation}</p>
                              <a className={styles.evalSource} href={item.source_url} target="_blank" rel="noreferrer">
                                <Link2 size={10} />
                                {item.source_label}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </section>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <button
              type="button"
              className={styles.panelToggle}
              onClick={() => setPanelOpen(true)}
              aria-label="展开右侧面板"
            >
              <PanelRight size={15} />
            </button>
          )}
        </aside>
      </div>

      <Modal
        open={evidenceTitle !== ''}
        title={`${evidenceTitle} · 依据`}
        description="以下为本次挖掘命中的公开信息线索。"
        width={520}
        onClose={() => setEvidenceTitle('')}
        footer={
          <Button variant="outline" onClick={() => setEvidenceTitle('')}>
            关闭
          </Button>
        }
      >
        <ul className={styles.evidenceList}>
          {evidenceItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={contactsRow !== null}
        title={contactsRow ? `${contactsRow.company_name} · 关键联系人` : '关键联系人'}
        description={contactsRow?.match_reason}
        width={620}
        onClose={() => setContactsRow(null)}
        footer={
          <Button variant="outline" onClick={() => setContactsRow(null)}>
            关闭
          </Button>
        }
      >
        {contactsLoading ? (
          <div className={styles.modalLoading}>
            <Spinner size={18} />
            <span>正在加载联系人…</span>
          </div>
        ) : contacts.length === 0 ? (
          <p className={styles.modalEmpty}>该企业暂未挖掘到关键联系人，可先重试字段。</p>
        ) : (
          <div className={styles.contactList}>
            {contacts.map((contact) => (
              <article key={contact.id} className={styles.contact}>
                <div className={styles.contactHead}>
                  <strong>{contact.name}</strong>
                  <Tag tone="primary">{contact.title}</Tag>
                  <span className={styles.contactConfidence}>置信度 {contact.confidence}%</span>
                </div>
                <dl className={styles.contactFields}>
                  <div>
                    <dt>邮箱</dt>
                    <dd>{contact.email}</dd>
                  </div>
                  <div>
                    <dt>电话</dt>
                    <dd>{contact.phone}</dd>
                  </div>
                  <div>
                    <dt>LinkedIn</dt>
                    <dd>{contact.linkedin}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </Modal>

      <Modal
        open={outreachOpen}
        title="创建智能触达计划"
        description="选择一个智能体与起始渠道，系统会生成一条多渠道序列。"
        onClose={() => setOutreachOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOutreachOpen(false)}>
              取消
            </Button>
            <Button variant="primary" loading={busy} onClick={() => void submitOutreach()}>
              创建计划
            </Button>
          </>
        }
      >
        <label className={styles.field}>
          <span className={styles.fieldLabel}>智能体</span>
          <select className={styles.select} value={agentName} onChange={(event) => setAgentName(event.target.value)}>
            {agentOptions.length === 0 ? <option value={defaultAgentName}>{defaultAgentName}</option> : null}
            {agentOptions.map((agent) => (
              <option key={agent.id} value={agent.name}>
                {agent.emoji} {agent.name}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span className={styles.fieldLabel}>起始渠道</span>
          <div className={styles.channelRow}>
            {OUTREACH_CHANNELS.map((item) => (
              <button
                key={item}
                type="button"
                className={[styles.channelChip, item === channel ? styles.channelChipActive : ''].filter(Boolean).join(' ')}
                onClick={() => setChannel(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </label>

        <p className={styles.fieldHint}>已选择 {selectedIds.length || rows.length} 家企业进入本轮触达。</p>
      </Modal>

      <Modal
        open={columnOpen}
        title="添加智能调研"
        description="用一句话描述要挖掘的字段，AI 会为每一行补充该字段的值。"
        onClose={() => setColumnOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setColumnOpen(false)}>
              取消
            </Button>
            <Button variant="primary" loading={busy} onClick={() => void addColumn()}>
              生成该列
            </Button>
          </>
        }
      >
        <label className={styles.field}>
          <span className={styles.fieldLabel}>字段描述</span>
          <input
            className={styles.input}
            placeholder="例如：是否已上线微信小程序"
            value={columnName}
            onChange={(event) => setColumnName(event.target.value)}
          />
        </label>
        <p className={styles.fieldHint}>
          已支持：小程序使用情况、招聘动作、技术栈、预算规模等。当前共 {columns.length} 列。
        </p>
      </Modal>
    </div>
  );
};

export default TargetDetailPage;
