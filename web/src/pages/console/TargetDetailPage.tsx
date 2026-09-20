// 潜客列表详情：数据表格 + 右侧「挖掘 / 详情」双面板。
// 挖掘面板负责编辑寻找对象与判断条件、解释挖掘策略、查看并追加进度；
// 点击表格任意一行后切到详情面板，展示该条记录的完整档案与准入条件评估。
//
// 列表有两种模式，**行结构不同**：会社行有行业/规模/融资/官网，人物行有姓名/职位/所属公司/档案地址。
// 本页据此分两套表头与两套行渲染，只在「首列、链接列、AI 摘要、综合结果、匹配分」上共用展示模型
// （见 `utils/target-rows`）——强行合并成一个行类型会让「字段缺失」与「字段为空」分不出来。

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
  Wrench,
  X,
} from 'lucide-react';

import * as agentsApi from '@/api/agents';
import * as targetsApi from '@/api/targets';
import type { Contact, TargetCompany, TargetCompanyDetail, TargetCondition, TargetList, TargetPerson, TargetPersonDetail } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import Modal from '@/components/Modal';
import Pagination from '@/components/Pagination';
import Spinner from '@/components/Spinner';
import Tag, { type TagTone } from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { CONDITION_COLORS, CATEGORY_LABELS, MINING_PHASE_LABELS } from '@/constants/targets';
import { OUTREACH_CHANNELS } from '@/constants/channels';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber, toDisplayDomain, toSourcePill } from '@/utils/format';
import { isPersonDetail, toCompanyDossier, toCompanyRow, toPersonDossier, toPersonRow } from '@/utils/target-rows';

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

/** 排序键两种模式共用（后端按行的标题/链接列取值），只有标签随模式改叫法。 */
const SORT_OPTIONS_BY_MODE = {
  company: [
    { key: 'match', label: '按相关度' },
    { key: 'name', label: '按公司名' },
    { key: 'website', label: '按网址' },
  ],
  people: [
    { key: 'match', label: '按相关度' },
    { key: 'name', label: '按姓名' },
    { key: 'website', label: '按档案地址' },
  ],
};

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
  // 列表模式决定表头、行结构、详情端点与排序标签，所以它在所有依赖它的 hook 之前先算出来。
  const isPeople = detail.data?.target_list.mode === 'people';
  // 数据源清单用于把列表上的 source_id 翻译成「这批结果是谁给的」
  const sources = useAsync(() => targetsApi.readSources());
  // 详情接口按模式分两个：人物档案与公司档案返回的字段集不同，不共用一个端点。
  // 泛型必须显式声明：加载函数返回的是「两个 Promise 的联合」，让 TS 自己推会只取到其中一支。
  const rowDetail = useAsync<TargetCompanyDetail | TargetPersonDetail | null>(
    () =>
      activeRowId === ''
        ? Promise.resolve(null)
        : isPeople
          ? targetsApi.readPersonDetail(listId, activeRowId)
          : targetsApi.readCompanyDetail(listId, activeRowId),
    { deps: [listId, activeRowId, isPeople] },
  );

  // 查询参数变化后清空选择，避免选中项与当前页数据不一致
  useEffect(() => setSelectedIds([]), [listId, page, keyword, matchLevel, sort]);

  const targetList: TargetList | null = detail.data?.target_list ?? null;
  const columns = detail.data?.columns ?? [];
  const companyPage = detail.data?.companies ?? null;
  const personPage = detail.data?.people ?? null;
  const companyRows = useMemo(() => companyPage?.items ?? [], [companyPage]);
  const personRows = useMemo(() => personPage?.items ?? [], [personPage]);
  const rowIds = useMemo(
    () => (isPeople ? personRows.map((row) => row.id) : companyRows.map((row) => row.id)),
    [isPeople, personRows, companyRows],
  );
  const total = (isPeople ? personPage?.total : companyPage?.total) ?? 0;
  const customColumns = useMemo(() => columns.filter((column) => !column.is_builtin), [columns]);
  const sortOptions = SORT_OPTIONS_BY_MODE[isPeople ? 'people' : 'company'];
  // References / 智能触达 / 智能调研 / 准入条件评估这几块在两种档案里是**同形**的，直接读原始数据；
  // 只有「头部 + 档案字段」要看行结构，交给展示模型适配。
  const dossier = rowDetail.data;
  const dossierView = useMemo(
    () => (dossier === null ? null : isPersonDetail(dossier) ? toPersonDossier(dossier) : toCompanyDossier(dossier)),
    [dossier],
  );

  const agentOptions = useMemo(() => agents.data ?? [], [agents.data]);
  const defaultAgentName = agentOptions[0]?.name ?? 'REVOR 默认销售智能体';

  const activeSource = useMemo(
    () => (sources.data ?? []).find((item) => item.id === targetList?.source_id) ?? null,
    [sources.data, targetList],
  );

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
  // 能否开始挖掘只看「有没有至少一条条件」：挖掘会先保存再重跑，
  // 配置没改动也允许重新挖一批，不需要逼用户再编辑一次。
  const canMine = conditions.some((item) => item.text.trim() !== '');

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
      rowDetail.reload();
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
        // 本地新增的行还没有经过标准引擎，权重与维度留空，保存后由后端补齐
        weight: 0,
        category: '',
        question: '',
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
      rowDetail.reload();
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
      showToast(`已追加 ${count} ${isPeople ? '位联系人' : '家企业'}`, 'success');
      detail.reload();
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '追加失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  /** 导出当前页。两种模式的行结构不同，表头与取值因此各写一份。 */
  const exportCsv = (): void => {
    const quote = (cell: string): string => `"${cell.replace(/"/g, '""')}"`;
    const rowsToLines = isPeople
      ? personRows.map((row) =>
          [
            row.name,
            row.name_local,
            row.company,
            row.title,
            row.source_url,
            row.ai_summary.replace(/\n/g, ' '),
            row.match_level,
            String(row.score),
          ].map(quote),
        )
      : companyRows.map((row) =>
          [
            row.company_name,
            row.website,
            row.industries.join(' / '),
            row.ai_summary.replace(/\n/g, ' '),
            row.match_level,
            String(row.score),
            String(row.contact_count),
          ].map(quote),
        );
    const header = isPeople
      ? ['名称', '中文名', '所属公司', '职位', '档案地址', 'AI 摘要', '综合结果', '匹配分']
      : ['所属公司', '网址', '行业', 'AI 摘要', '综合结果', '匹配分', '联系人数'];
    const lines = rowsToLines.map((cells) => cells.join(','));
    const blob = new Blob([`\uFEFF${[header.join(','), ...lines].join('\n')}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ai-get-潜客列表-${targetList?.id ?? 'export'}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('已导出当前页数据', 'success');
  };

  const allSelected = rowIds.length > 0 && rowIds.every((rowId) => selectedIds.includes(rowId));

  const toggleAll = (): void => {
    setSelectedIds(allSelected ? [] : rowIds);
  };

  const toggleRow = (rowId: string): void => {
    setSelectedIds((current) => (current.includes(rowId) ? current.filter((id) => id !== rowId) : [...current, rowId]));
  };

  /** 会社行：所属公司 / 网址 / 行业 / AI 摘要 / 综合结果 / 匹配分 / 两列内置调研列。 */
  const renderCompanyRow = (row: TargetCompany, index: number): JSX.Element => {
    const view = toCompanyRow(row);
    return (
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
            aria-label={`选择 ${view.title}`}
          />
        </td>
        <td className={styles.indexCell}>{(page - 1) * PAGE_SIZE + index + 1}</td>
        <td>
          <div className={styles.companyCell}>
            <span className={styles.companyMark}>{view.mark}</span>
            <div className={styles.companyText}>
              <strong>{view.title}</strong>
              <small>{view.subtitle}</small>
            </div>
          </div>
        </td>
        <td onClick={(event) => event.stopPropagation()}>
          <a className={styles.website} href={view.linkHref} target="_blank" rel="noreferrer">
            <Globe size={12} />
            {view.linkLabel}
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
        <td>
          <span className={styles.score}>{row.score}</span>
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
            <span className={styles.customValue}>{view.customValues[column.id] ?? '—'}</span>
          </td>
        ))}
        <td className={styles.actionCell}>
          <button
            type="button"
            className={styles.rowAction}
            aria-label={`查看 ${view.title} 详情`}
            onClick={(event) => {
              event.stopPropagation();
              selectRow(row.id);
            }}
          >
            <Info size={14} />
          </button>
        </td>
      </tr>
    );
  };

  /** 人物行：姓名 / 所属公司 / 职位 / 档案地址 / AI 摘要 / 综合结果 / 匹配分。
   *
   * 人物侧没有「重试富化」入口：后端只对公司行开放该接口，
   * 人在这张表里是**检索结果**，摘要与联系方式的补全走详情面板的智能调研。
   */
  const renderPersonRow = (row: TargetPerson, index: number): JSX.Element => {
    const view = toPersonRow(row);
    return (
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
            aria-label={`选择 ${view.title}`}
          />
        </td>
        <td className={styles.indexCell}>{(page - 1) * PAGE_SIZE + index + 1}</td>
        <td>
          <div className={styles.companyCell}>
            <span className={styles.companyMark}>{view.mark}</span>
            <div className={styles.companyText}>
              <strong>{view.title}</strong>
              <small>{view.subtitle}</small>
            </div>
          </div>
        </td>
        <td>{row.company}</td>
        <td>
          <Tag tone="neutral">{row.title}</Tag>
        </td>
        <td onClick={(event) => event.stopPropagation()}>
          <a className={styles.website} href={view.linkHref} target="_blank" rel="noreferrer">
            <Link2 size={12} />
            {view.linkLabel}
          </a>
        </td>
        <td className={styles.summaryCell}>
          {row.summary_state === 'ready' ? (
            <p className={styles.summaryText}>{row.ai_summary}</p>
          ) : (
            <span className={styles.muted}>摘要尚未生成</span>
          )}
        </td>
        <td>
          <Tag tone={MATCH_TONES[row.match_level] ?? 'neutral'}>{row.match_level}</Tag>
        </td>
        <td>
          <span className={styles.score}>{row.score}</span>
        </td>
        {customColumns.map((column) => (
          <td key={column.id}>
            <span className={styles.customValue}>{view.customValues[column.id] ?? '—'}</span>
          </td>
        ))}
        <td className={styles.actionCell}>
          <button
            type="button"
            className={styles.rowAction}
            aria-label={`查看 ${view.title} 详情`}
            onClick={(event) => {
              event.stopPropagation();
              selectRow(row.id);
            }}
          >
            <Info size={14} />
          </button>
        </td>
      </tr>
    );
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
  const rowUnit = isPeople ? '位联系人' : '家企业';

  return (
    <div className={styles.page}>
      <header className={styles.toolbar}>
        <Link className={styles.back} to={ROUTES.consoleTargets} aria-label="返回潜客挖掘">
          <ArrowLeft size={16} />
        </Link>

        <div className={styles.toolbarTitle}>
          <p className={styles.toolbarQuery}>{targetList.query}</p>
          <div className={styles.toolbarMeta}>
            <Tag tone={running ? 'warning' : 'success'}>
              {running ? MINING_PHASE_LABELS[targetList.phase ?? 'searching'] ?? '进行中' : '已完成'}
            </Tag>
            <span>
              {formatNumber(targetList.discovered_count)} / {formatNumber(targetList.requested_count)} {rowUnit}
            </span>
            {isPeople ? null : <span>已获取联系人 {formatNumber(targetList.contact_count)} 位</span>}
            {targetList.source_name ? <span>数据源 {targetList.source_name}</span> : null}
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
            items={sortOptions}
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
            disabled={selectedIds.length === 0 && rowIds.length === 0}
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
                  {isPeople ? (
                    <>
                      <th>名称</th>
                      <th>所属公司</th>
                      <th>职位</th>
                      <th>档案地址</th>
                    </>
                  ) : (
                    <>
                      <th>所属公司</th>
                      <th>网址</th>
                      <th>行业</th>
                    </>
                  )}
                  <th className={styles.summaryCell}>AI 摘要</th>
                  <th>综合结果</th>
                  <th>匹配分</th>
                  {isPeople ? null : (
                    <>
                      <th>企业关键联系人挖掘</th>
                      <th>官网联系方式挖掘</th>
                    </>
                  )}
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
              <tbody>{isPeople ? personRows.map(renderPersonRow) : companyRows.map(renderCompanyRow)}</tbody>
            </table>
          </div>

          {rowIds.length === 0 && !detail.loading ? (
            <div className={styles.emptyRows}>
              {running ? '正在挖掘中，稍后会陆续出现结果…' : `没有符合当前筛选条件的${isPeople ? '联系人' : '企业'}`}
            </div>
          ) : null}

          <footer className={styles.tableFooter}>
            <input
              className={styles.search}
              placeholder={isPeople ? '搜索姓名、公司或职位…' : '搜索公司名、行业或摘要…'}
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
                      <span className={styles.cardHint}>
                        {conditions.length} 条 · 权重合计 {conditions.reduce((sum, item) => sum + item.weight, 0)}
                      </span>
                    </header>

                    {/* 标准会被冻结进任务记录，标出产出方才能解释「为什么这批结论是这样」。
                        降级原因单独用警示色：它代表「本可以更好」，而不是信息。 */}
                    {targetList.criteria_label ? (
                      <p className={styles.criteriaSource}>
                        {targetList.criteria_source === 'llm' ? <Sparkles size={12} /> : <Wrench size={12} />}
                        <span>
                          标准引擎 <strong>{targetList.criteria_label}</strong>
                        </span>
                        {targetList.criteria_fallback_reason ? (
                          <span className={styles.criteriaFallback}>
                            已降级 · {targetList.criteria_fallback_reason}
                          </span>
                        ) : null}
                      </p>
                    ) : null}

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
                          {condition.category !== '' || condition.weight > 0 ? (
                            <span className={styles.conditionMeta} title={condition.question || undefined}>
                              <span className={styles.conditionCategory}>
                                {CATEGORY_LABELS[condition.category] ?? condition.category}
                              </span>
                              {condition.weight > 0 ? <em className={styles.conditionWeight}>{condition.weight}</em> : null}
                            </span>
                          ) : null}
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
                      disabled={busy || !canMine}
                      title={canMine ? undefined : '至少保留一条判断条件后才能挖掘'}
                      onClick={() => void startMining()}
                    >
                      <Search size={15} />
                      开始挖掘
                    </button>
                    {canMine ? null : (
                      <p className={styles.configHint}>请先添加或保留至少一条判断条件。</p>
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
                      {running
                        ? `${MINING_PHASE_LABELS[targetList.phase ?? 'searching'] ?? '挖掘中'}：正在实时检索匹配企业并富化字段…`
                        : '本轮挖掘已完成，可继续追加更多结果。'}
                    </p>

                    {targetList.progress_detail ? (
                      <dl className={styles.progressSteps}>
                        <div>
                          <dt>目标</dt>
                          <dd>{formatNumber(targetList.progress_detail.goal)}</dd>
                        </div>
                        <div>
                          <dt>已校验</dt>
                          <dd>{formatNumber(targetList.progress_detail.verified)}</dd>
                        </div>
                        <div>
                          <dt>已达标</dt>
                          <dd>{formatNumber(targetList.progress_detail.qualified)}</dd>
                        </div>
                        <div>
                          <dt>完全匹配</dt>
                          <dd>{formatNumber(targetList.progress_detail.full)}</dd>
                        </div>
                      </dl>
                    ) : null}

                    {targetList.progress_detail?.stop_reason ? (
                      <p className={styles.stopReason}>{targetList.progress_detail.stop_reason}</p>
                    ) : null}

                    {targetList.source_name ? (
                      <p className={styles.sourceLine}>
                        数据源 <strong>{targetList.source_name}</strong>
                        {activeSource ? ` · ${activeSource.description}` : ''}
                      </p>
                    ) : null}

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
                    <p className={styles.dossierEmpty}>
                      点击左侧任意一行{isPeople ? '联系人' : '企业'}，查看它的详细档案与准入条件评估。
                    </p>
                  ) : rowDetail.loading && dossier === null ? (
                    <div className={styles.dossierLoading}>
                      <Spinner size={18} />
                      <span>正在读取详细档案…</span>
                    </div>
                  ) : dossier === null || dossierView === null ? (
                    <p className={styles.dossierEmpty}>{rowDetail.error ?? '未能读取该条记录的详细档案。'}</p>
                  ) : (
                    <div className={styles.dossier}>
                      <header className={styles.dossierHead}>
                        <span className={styles.dossierLabel}>详细档案</span>
                        <h3 className={styles.dossierName}>{dossierView.name}</h3>
                        <span className={styles.dossierBadge}>{dossierView.badge}</span>
                        <a
                          className={styles.dossierLink}
                          href={dossierView.linkHref}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Link2 size={11} />
                          {dossierView.linkLabel}
                        </a>
                      </header>

                      <section className={styles.dossierBlock}>
                        <span className={styles.blockLabel}>AI 摘要</span>
                        <p className={styles.blockText}>
                          {dossierView.summary || '摘要尚未生成，可在表格中对该字段发起重新富化。'}
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
                        {dossierView.fields.map((field) => (
                          <div key={field.label}>
                            <dt>{field.label}</dt>
                            <dd>{field.value}</dd>
                          </div>
                        ))}
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
                                {item.weight > 0 ? (
                                  <span className={styles.evalWeight}>权重 {item.weight}</span>
                                ) : null}
                                <span className={styles.evalRef}>参考 {item.reference_count}</span>
                              </div>
                              <p className={styles.evalText}>{item.explanation}</p>
                              <div className={styles.evalSources}>
                                {(item.references.length > 0
                                  ? item.references
                                  : item.source_url !== ''
                                    ? [{ title: item.source_label, url: item.source_url }]
                                    : []
                                ).map((ref) => (
                                  <a
                                    key={ref.url}
                                    className={styles.evalSource}
                                    href={ref.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    title={ref.title}
                                  >
                                    <Link2 size={10} />
                                    {toSourcePill(ref.url)}
                                  </a>
                                ))}
                              </div>
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

        <p className={styles.fieldHint}>
          已选择 {selectedIds.length || rowIds.length} {rowUnit}进入本轮触达。
        </p>
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
