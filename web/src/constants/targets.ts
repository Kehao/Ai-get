// 潜客挖掘的展示常量。
// 条件色条的颜色由后端按位置循环下发，这里保留同一份色板，
// 仅用于本地新增条件行在保存前的颜色预览。
export const CONDITION_COLORS: string[] = ['#8b5cf6', '#fb923c', '#0ea5e9', '#10b981'];

/** 挖掘状态机的阶段文案，顺序与后端 phase 推进一致。 */
export const MINING_PHASE_LABELS: Record<string, string> = {
  generating_criteria: '生成标准',
  searching: '检索候选',
  verifying: '资格校验',
  completed: '已完成',
};

/** 标准维度文案：把后端的英文 category 翻成用户能读懂的词。 */
export const CATEGORY_LABELS: Record<string, string> = {
  geo: '地域',
  industry: '行业',
  size: '规模',
  funding: '融资',
  business: '业务特征',
  signal: '信号',
  reachability: '可达性',
};
