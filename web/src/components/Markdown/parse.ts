// 极简 Markdown 解析：只覆盖背调报告实际用到的语法。
// 解析成结构化数据后由 React 渲染成元素，全程不使用 dangerouslySetInnerHTML。

export type MarkdownBlock =
  | { type: 'heading'; level: 1 | 2 | 3; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'table'; header: string[]; rows: string[][] };

export type InlineToken = { type: 'text' | 'strong' | 'code'; text: string };

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g;
const HEADING_PATTERN = /^(#{1,3})\s+(.*)$/;
const BULLET_PATTERN = /^\s*[-*]\s+(.*)$/;
const ORDERED_PATTERN = /^\s*\d+\.\s+(.*)$/;
const TABLE_SEPARATOR_PATTERN = /^\|?[\s:|-]+\|?$/;

export const parseInline = (text: string): InlineToken[] => {
  const tokens: InlineToken[] = [];
  let cursor = 0;

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      tokens.push({ type: 'text', text: text.slice(cursor, start) });
    }

    const raw = match[0];
    if (raw.startsWith('**')) {
      tokens.push({ type: 'strong', text: raw.slice(2, -2) });
    } else {
      tokens.push({ type: 'code', text: raw.slice(1, -1) });
    }
    cursor = start + raw.length;
  }

  if (cursor < text.length) {
    tokens.push({ type: 'text', text: text.slice(cursor) });
  }
  return tokens;
};

export const parseMarkdown = (source: string): MarkdownBlock[] => {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const heading = HEADING_PATTERN.exec(line);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length as 1 | 2 | 3, text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (line.trim().startsWith('|')) {
      const table = readTable(lines, index);
      if (table) {
        blocks.push(table.block);
        index = table.nextIndex;
        continue;
      }
    }

    if (BULLET_PATTERN.test(line) || ORDERED_PATTERN.test(line)) {
      const list = readList(lines, index);
      blocks.push(list.block);
      index = list.nextIndex;
      continue;
    }

    const paragraph = readParagraph(lines, index);
    blocks.push({ type: 'paragraph', text: paragraph.text });
    index = paragraph.nextIndex;
  }

  return blocks;
};

const readTable = (lines: string[], start: number): { block: MarkdownBlock; nextIndex: number } | null => {
  const header = splitRow(lines[start]);
  const separator = lines[start + 1] ? splitRow(lines[start + 1]) : [];
  if (header.length === 0 || separator.length === 0 || !separator.every((cell) => TABLE_SEPARATOR_PATTERN.test(cell))) {
    return null;
  }

  const rows: string[][] = [];
  let index = start + 2;
  while (index < lines.length && lines[index].trim().startsWith('|')) {
    rows.push(splitRow(lines[index]));
    index += 1;
  }
  return { block: { type: 'table', header, rows }, nextIndex: index };
};

const splitRow = (line: string): string[] =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());

const readList = (lines: string[], start: number): { block: MarkdownBlock; nextIndex: number } => {
  const ordered = ORDERED_PATTERN.test(lines[start]);
  const pattern = ordered ? ORDERED_PATTERN : BULLET_PATTERN;
  const items: string[] = [];
  let index = start;

  while (index < lines.length) {
    const matched = pattern.exec(lines[index]);
    if (!matched) {
      break;
    }
    items.push(matched[1].trim());
    index += 1;
  }
  return { block: { type: 'list', ordered, items }, nextIndex: index };
};

const readParagraph = (lines: string[], start: number): { text: string; nextIndex: number } => {
  const chunks: string[] = [];
  let index = start;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim() || HEADING_PATTERN.test(line) || line.trim().startsWith('|') || BULLET_PATTERN.test(line) || ORDERED_PATTERN.test(line)) {
      break;
    }
    chunks.push(line.trim());
    index += 1;
  }
  return { text: chunks.join(' '), nextIndex: index };
};
