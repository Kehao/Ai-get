// 展示层格式化工具。

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期。 */
export const formatRelativeTime = (isoText: string, now: Date = new Date()): string => {
  const moment = new Date(isoText);
  const diff = now.getTime() - moment.getTime();

  if (Number.isNaN(diff)) {
    return '';
  }
  if (diff < MINUTE) {
    return '刚刚';
  }
  if (diff < HOUR) {
    return `${Math.floor(diff / MINUTE)} 分钟前`;
  }
  if (diff < DAY) {
    return `${Math.floor(diff / HOUR)} 小时前`;
  }
  if (diff < 30 * DAY) {
    return `${Math.floor(diff / DAY)} 天前`;
  }
  return formatDate(moment);
};

export const formatDate = (moment: Date): string => `${moment.getMonth() + 1}月${moment.getDate()}日`;

/** 月日 + 时分，用于「更新于 9月16日 23:22」。 */
export const formatDateTime = (isoText: string): string => {
  const moment = new Date(isoText);
  if (Number.isNaN(moment.getTime())) {
    return '';
  }
  const time = `${String(moment.getHours()).padStart(2, '0')}:${String(moment.getMinutes()).padStart(2, '0')}`;
  return `${formatDate(moment)} ${time}`;
};

/** 完整日期时间，用于详情页「创建时间 2026/09/16 00:22」。 */
export const formatFullDateTime = (isoText: string): string => {
  const moment = new Date(isoText);
  if (Number.isNaN(moment.getTime())) {
    return '';
  }
  const date = [moment.getFullYear(), moment.getMonth() + 1, moment.getDate()]
    .map((part, index) => (index === 0 ? String(part) : String(part).padStart(2, '0')))
    .join('/');
  const time = `${String(moment.getHours()).padStart(2, '0')}:${String(moment.getMinutes()).padStart(2, '0')}`;
  return `${date} ${time}`;
};

/** 千分位数字。 */
export const formatNumber = (value: number): string => value.toLocaleString('zh-CN');

/** 截断长文本，超出部分用省略号。 */
export const truncate = (text: string, limit: number): string =>
  text.length <= limit ? text : `${text.slice(0, limit)}…`;

/** 去掉协议前缀的域名，用于表格中展示网址。 */
export const toDisplayDomain = (url: string): string => url.replace(/^https?:\/\//, '');

/** 取域名首字母作为企业标识块的文字。 */
export const toDomainInitial = (url: string): string => {
  const domain = toDisplayDomain(url);
  return domain.slice(0, 2).toUpperCase();
};
