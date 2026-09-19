// 潜客列表的两种行结构（公司 / 人物）到「表格与详情面板展示模型」的适配。
//
// 后端刻意让两种模式返回**结构不同**的行：公司看行业、规模、融资、官网，
// 人物看姓名、职位、所属公司与档案地址。前端**不把它们合并成一个类型**
// （合并后「字段缺失」与「字段为空」就分不出来了），而是各自适配到同一个展示模型，
// 让表格与详情面板只保留一套渲染逻辑。

import type { FieldState, MatchLevel, TargetCompany, TargetCompanyDetail, TargetPerson, TargetPersonDetail } from '@/api/types';
import { formatFullDateTime, toDisplayDomain, toDomainInitial } from '@/utils/format';

/** 详情面板里的一行档案字段。 */
export interface DossierField {
  label: string;
  value: string;
}

/** 详情面板的展示模型：两种档案共用的那部分。 */
export interface DossierView {
  name: string;
  /** 档案类型角标，与参考站一致用小写。 */
  badge: string;
  linkLabel: string;
  linkHref: string;
  summary: string;
  fields: DossierField[];
}

/** 表格行的展示模型。首列与链接列两种模式都长一个样，中段与尾部按模式各渲染各的。 */
export interface RowView {
  id: string;
  /** 首列主标题：公司名 / 姓名。 */
  title: string;
  /** 首列角标字符：官网首字母 / 姓名首字。 */
  mark: string;
  /** 首列副标题：人物写职位，公司写地区·规模·融资。 */
  subtitle: string;
  linkLabel: string;
  linkHref: string;
  aiSummary: string;
  summaryState: FieldState;
  matchLevel: MatchLevel;
  score: number;
  customValues: Record<string, string>;
}

export const toCompanyRow = (row: TargetCompany): RowView => ({
  id: row.id,
  title: row.company_name,
  mark: toDomainInitial(row.website),
  subtitle: [row.location, row.employees, row.funding_stage].filter((part) => part !== '').join(' · '),
  linkLabel: toDisplayDomain(row.website),
  linkHref: `https://${toDisplayDomain(row.website)}`,
  aiSummary: row.ai_summary,
  summaryState: row.summary_state,
  matchLevel: row.match_level,
  score: row.score,
  customValues: row.custom_values,
});

export const toPersonRow = (row: TargetPerson): RowView => ({
  id: row.id,
  // 人物的区域单独占「所属公司」「职位」两列，所以首列只放姓名本身，副标题补中文名与所在地。
  title: row.name,
  mark: row.name.slice(0, 1).toUpperCase(),
  subtitle: [row.name_local, row.location].filter((part) => part !== '').join(' · '),
  linkLabel: `${row.source_label} · ${toDisplayDomain(row.source_url)}`,
  linkHref: row.source_url,
  aiSummary: row.ai_summary,
  summaryState: row.summary_state,
  matchLevel: row.match_level,
  score: row.score,
  customValues: row.custom_values,
});

/**
 * 详情响应的判别式。
 *
 * 两种详情响应的判别键不同（人物带 `person`、公司带 `company`），
 * 写成显式类型谓词而不是让调用方用 `in` 临时收窄：调用点一旦多起来，
 * 每处都要重复一遍同样的收窄逻辑，漏写一处就是运行期取错字段。
 */
export const isPersonDetail = (
  detail: TargetCompanyDetail | TargetPersonDetail,
): detail is TargetPersonDetail => 'person' in detail;

export const toCompanyDossier = (detail: TargetCompanyDetail): DossierView => ({  name: detail.company.company_name,
  badge: 'company',
  linkLabel: toDisplayDomain(detail.company.website),
  linkHref: `https://${toDisplayDomain(detail.company.website)}`,
  summary: detail.company.ai_summary,
  fields: [
    { label: '名称', value: detail.company.company_name },
    { label: '行业', value: detail.company.industries.join('、') },
    { label: '地区', value: detail.company.location },
    { label: '规模', value: `${detail.company.employees} · ${detail.company.funding_stage}` },
    { label: '匹配分', value: String(detail.company.score) },
    { label: '创建时间', value: formatFullDateTime(detail.company.created_at) },
  ],
});

export const toPersonDossier = (detail: TargetPersonDetail): DossierView => ({
  name: detail.person.name_local === '' ? detail.person.name : detail.person.name_local,
  badge: 'person',
  linkLabel: toDisplayDomain(detail.person.source_url),
  linkHref: detail.person.source_url,
  summary: detail.person.ai_summary,
  fields: [
    { label: '名称', value: detail.person.name },
    { label: '公司', value: detail.person.company },
    { label: '职位', value: detail.person.title },
    { label: '地区', value: detail.person.location },
    { label: '匹配分', value: String(detail.person.score) },
    { label: '创建时间', value: formatFullDateTime(detail.person.created_at) },
  ],
});
