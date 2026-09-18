// 商机洞察：互动指标、智能体工作进展与值得跟进的商机列表。

import { useEffect, useMemo, useState } from 'react';
import { Activity, ChevronDown, Sparkles } from 'lucide-react';

import * as opportunitiesApi from '@/api/opportunities';
import type { OpportunityItem, OpportunityLevel, OpportunityRange } from '@/api/types';
import Dropdown from '@/components/Dropdown';
import EmptyState from '@/components/EmptyState';
import LineChart from '@/components/LineChart';
import Pagination from '@/components/Pagination';
import SegmentedControl from '@/components/SegmentedControl';
import Spinner from '@/components/Spinner';
import Tag from '@/components/Tag';
import { useAsync } from '@/hooks/useAsync';
import { formatNumber, formatRelativeTime, truncate } from '@/utils/format';

import styles from './OpportunitiesPage.module.less';

const RANGE_OPTIONS: { value: OpportunityRange; label: string }[] = [
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: '12m', label: '12 个月' },
];

const AGENT_ITEMS = [{ key: 'all', label: '全部智能体', description: '包含所有已发布的销售智能体' }];

/** 商机渠道与执行触达的智能体一一对应。 */
const toAgentName = (channel: string): string => `${channel}智能体`;

const LEVEL_TONES = { 建议跟进: 'success', 初步信号: 'warning', 暂无信号: 'neutral' } as const;
const LEVELS: OpportunityLevel[] = ['建议跟进', '初步信号', '暂无信号'];
const PAGE_SIZE = 8;

const OpportunitiesPage = (): JSX.Element => {
  const [range, setRange] = useState<OpportunityRange>('7d');
  const [level, setLevel] = useState<OpportunityLevel | 'all'>('all');
  const [page, setPage] = useState(1);

  const overview = useAsync(() => opportunitiesApi.readOpportunities(range), {
    deps: [range],
  });

  const opportunities = useMemo(() => overview.data?.opportunities ?? [], [overview.data]);

  const filtered = useMemo(
    () => (level === 'all' ? opportunities : opportunities.filter((item) => item.level === level)),
    [opportunities, level],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visibleRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // 切换时间范围或结论筛选后回到第一页，避免停留在已不存在的页码上
  useEffect(() => setPage(1), [range, level]);

  const levelCounts = overview.data?.level_counts ?? {};
  const totalCount = opportunities.length;

  if (overview.loading && overview.data === null) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在加载商机数据…</span>
      </div>
    );
  }

  if (overview.error !== null && overview.data === null) {
    return <EmptyState title="商机数据不可用" description={overview.error} />;
  }

  const data = overview.data;

  return (
    <div className={styles.page}>
      <section className={styles.topBar}>
        <div className={styles.topInfo}>
          <span className={styles.topIcon}>
            <Activity size={18} />
          </span>
          <div className={styles.topText}>
            <h1 className={styles.topTitle}>{data?.today_task_label ?? '今天暂无客户开发任务'}</h1>
            <p className={styles.topSubtitle}>{data?.follow_up_label ?? '暂无后续开发计划'}</p>
          </div>
        </div>

        <div className={styles.topActions}>
          <Dropdown
            panelWidth={240}
            items={AGENT_ITEMS}
            onSelect={() => undefined}
            trigger={({ open }) => (
              <button
                type="button"
                className={[styles.agentButton, open ? styles.agentButtonOpen : ''].filter(Boolean).join(' ')}
              >
                全部智能体
                <ChevronDown size={14} />
              </button>
            )}
          />

          <SegmentedControl
            options={RANGE_OPTIONS}
            value={range}
            onChange={setRange}
            ariaLabel="数据时间范围"
          />
        </div>
      </section>

      <section className={styles.kpiRow}>
        {(data?.kpis ?? []).map((kpi) => (
          <article key={kpi.key} className={styles.kpiCard}>
            <span className={styles.kpiLabel}>{kpi.label}</span>
            <span className={styles.kpiValue}>{formatNumber(kpi.value)}</span>
            <span className={styles.kpiCaption}>{kpi.caption}</span>
          </article>
        ))}
      </section>

      <section className={styles.insightRow}>
        <article className={styles.chartCard}>
          <header className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>智能体工作进展</h2>
            <p className={styles.cardSubtitle}>客户互动与重点商机</p>
          </header>
          <LineChart points={data?.chart ?? []} />
        </article>

        <article className={styles.activityCard}>
          <header className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>AI 动态</h2>
            <p className={styles.cardSubtitle}>每日工作成果与商机信号</p>
          </header>

          {(data?.activity ?? []).length === 0 ? (
            <p className={styles.activityEmpty}>最近还没有新的触达或客户回复</p>
          ) : (
            <ul className={styles.activityList}>
              {(data?.activity ?? []).map((item) => (
                <li key={item.id} className={styles.activityItem}>
                  <span className={styles.activityDot} />
                  <div className={styles.activityBody}>
                    <h3 className={styles.activityTitle}>{item.title}</h3>
                    <p className={styles.activityDetail}>{item.detail}</p>
                    <span className={styles.activityTime}>{formatRelativeTime(item.happened_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>

      <section className={styles.listSection}>
        <header className={styles.listHeader}>
          <div className={styles.listHeading}>
            <h2 className={styles.listTitle}>商机列表</h2>
            <Tag tone="primary" size="md">
              AI 商机分析
            </Tag>
          </div>
          <p className={styles.listSubtitle}>重点关注高意向商机</p>
        </header>

        <div className={styles.listToolbar}>
          <span className={styles.analyzed}>
            已完成分析 <strong>{data?.analyzed_percent ?? 0}%</strong>
          </span>

          <div className={styles.filters}>
            <button
              type="button"
              className={[styles.filter, level === 'all' ? styles.filterActive : ''].filter(Boolean).join(' ')}
              onClick={() => setLevel('all')}
            >
              全部 <strong>{totalCount}</strong>
            </button>

            {LEVELS.map((item) => (
              <button
                key={item}
                type="button"
                className={[styles.filter, level === item ? styles.filterActive : ''].filter(Boolean).join(' ')}
                onClick={() => setLevel(item)}
              >
                {item} <strong>{levelCounts[item] ?? 0}</strong>
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            compact
            title="暂时没有符合条件的商机"
            description="调整结论筛选或时间范围后再看看。"
          />
        ) : (
          <>
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.colCompany}>客户</th>
                    <th className={styles.colSignal}>客户信号</th>
                    <th className={styles.colConclusion}>AI 结论</th>
                    <th className={styles.colAgent}>智能体</th>
                    <th className={styles.colChannel}>渠道</th>
                    <th className={styles.colTime}>最近互动时间</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <OpportunityRow key={row.id} row={row} />
                  ))}
                </tbody>
              </table>
            </div>

            <footer className={styles.listFooter}>
              <Pagination page={currentPage} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} />
            </footer>
          </>
        )}
      </section>

      <p className={styles.footnote}>
        <Sparkles size={13} />
        商机结论由 AI 根据互动记录自动生成，建议结合实际沟通进度判断优先级。
      </p>
    </div>
  );
};

const OpportunityRow = ({ row }: { row: OpportunityItem }): JSX.Element => (
  <tr className={styles.row}>
    <td>
      <div className={styles.companyCell}>
        <span className={styles.contactAvatar}>{row.contact_name.slice(0, 1)}</span>
        <div className={styles.companyText}>
          <strong>{row.company_name}</strong>
          <span>{row.contact_name}</span>
        </div>
      </div>
    </td>
    <td>
      <span className={styles.signal}>{row.signal}</span>
    </td>
    <td>
      <div className={styles.conclusionCell}>
        <Tag tone={LEVEL_TONES[row.level]}>{row.level}</Tag>
        <p className={styles.conclusionText}>{truncate(row.summary, 46)}</p>
      </div>
    </td>
    <td>{toAgentName(row.channel)}</td>
    <td>
      <Tag tone="neutral" outline>
        {row.channel}
      </Tag>
    </td>
    <td className={styles.timeCell}>{formatRelativeTime(row.last_message_at)}</td>
  </tr>
);

export default OpportunitiesPage;
