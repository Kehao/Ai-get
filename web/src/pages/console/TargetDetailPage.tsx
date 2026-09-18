// 潜客列表详情：数据表格 + 右侧条件与挖掘进度面板。
// 表格列由后端下发（内置列 + 自定义富化列），工具栏提供筛选、排序、智能触达与新增调研列。

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpDown,
  Download,
  Filter,
  Info,
  MoreHorizontal,
  RefreshCw,
  Send,
  Sparkles,
  UserPlus,
} from 'lucide-react';

import * as agentsApi from '@/api/agents';
import * as targetsApi from '@/api/targets';
import type { Contact, TargetCompany, TargetList } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import Modal from '@/components/Modal';
import Pagination from '@/components/Pagination';
import ProgressBar from '@/components/ProgressBar';
import Spinner from '@/components/Spinner';
import Tag, { type TagTone } from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { OUTREACH_CHANNELS } from '@/constants/channels';
import { ROUTES } from '@/constants/routes';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber, toDisplayDomain, toDomainInitial } from '@/utils/format';

import styles from './TargetDetailPage.module.less';

const PAGE_SIZE = 20;
const MATCH_TONES: Record<string, TagTone> = {
  明确符合: 'success',
  可能符合: 'warning',
  待确认: 'neutral',
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

const TargetDetailPage = (): JSX.Element => {
  const { listId = '' } = useParams();
  const { showToast } = useToast();

  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [matchLevel, setMatchLevel] = useState('');
  const [sort, setSort] = useState('match');

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
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '重新富化失败', 'error');
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
            items={[{ key: 'refresh', label: '刷新数据' }]}
            onSelect={() => detail.reload()}
            trigger={({ open }) => (
              <button type="button" className={[styles.toolButton, open ? styles.toolButtonOpen : ''].filter(Boolean).join(' ')}>
                <MoreHorizontal size={15} />
                更多
              </button>
            )}
          />

          <button type="button" className={styles.toolButton} onClick={exportCsv}>
            <Download size={15} />
            导出
          </button>

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
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className={styles.checkCell}>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(row.id)}
                        onChange={() => toggleRow(row.id)}
                        aria-label={`选择 ${row.company_name}`}
                      />
                    </td>
                    <td>
                      <div className={styles.companyCell}>
                        <span className={styles.companyMark}>{toDomainInitial(row.website)}</span>
                        <div className={styles.companyText}>
                          <strong>{row.company_name}</strong>
                          <small>{row.location} · {row.employees} · {row.funding_stage}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <a
                        className={styles.website}
                        href={`https://${toDisplayDomain(row.website)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
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
                        <button type="button" className={styles.retryButton} onClick={() => void retryField(row, 'summary')}>
                          <RefreshCw size={13} />
                          重试生成摘要
                        </button>
                      )}
                    </td>
                    <td>
                      <Tag tone={MATCH_TONES[row.match_level] ?? 'neutral'}>{row.match_level}</Tag>
                    </td>
                    <td>
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
                    <td>
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
                      <button type="button" className={styles.rowAction} onClick={() => void openContacts(row)}>
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

        <aside className={styles.panel}>
          <div className={styles.panelTabs}>
            <span className={styles.panelTabActive}>挖掘</span>
            <span className={styles.panelTab}>详情</span>
          </div>

          <section className={styles.panelSection}>
            <header className={styles.panelHeader}>
              <span className={styles.panelIcon}>📌</span>
              <h3>条件</h3>
            </header>
            <div className={styles.conditionList}>
              {targetList.conditions.map((condition) => (
                <span key={condition} className={styles.condition}>
                  {condition}
                </span>
              ))}
            </div>
          </section>

          <section className={styles.panelSection}>
            <header className={styles.panelHeader}>
              <span className={styles.panelIcon}>📈</span>
              <h3>挖掘进度</h3>
              <span className={styles.progressValue}>
                {targetList.discovered_count} / {targetList.requested_count}
              </span>
            </header>
            <ProgressBar value={targetList.progress} tone={running ? 'primary' : 'success'} />
            <p className={styles.progressHint}>
              {running ? '正在实时检索匹配企业并富化字段…' : '本轮挖掘已完成，可继续追加更多结果。'}
            </p>

            <div className={styles.moreButtons}>
              {[25, 100, 500, 1000].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={styles.moreChip}
                  disabled={busy}
                  onClick={() => void addMore(value)}
                >
                  {value}
                </button>
              ))}
            </div>

            <Button variant="gradient" block loading={busy} onClick={() => void addMore(25)}>
              挖掘更多
            </Button>
          </section>

          <section className={styles.panelSection}>
            <header className={styles.panelHeader}>
              <span className={styles.panelIcon}>🎯</span>
              <h3>跟进计划</h3>
            </header>
            <p className={styles.progressHint}>{targetList.follow_up_plan ?? '暂无跟进计划，可先创建智能触达。'}</p>
          </section>
        </aside>
      </div>

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
