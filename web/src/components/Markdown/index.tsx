// Markdown 渲染组件：把背调报告的结构化块渲染成 React 元素。

import type { ReactNode } from 'react';

import { parseInline, parseMarkdown, type MarkdownBlock } from './parse';
import styles from './Markdown.module.less';

interface MarkdownProps {
  source: string;
}

const renderInline = (text: string, keyPrefix: string): ReactNode[] =>
  parseInline(text).map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (token.type === 'strong') {
      return <strong key={key}>{token.text}</strong>;
    }
    if (token.type === 'code') {
      return <code key={key}>{token.text}</code>;
    }
    return <span key={key}>{token.text}</span>;
  });

const renderBlock = (block: MarkdownBlock, index: number): ReactNode => {
  const key = `block-${index}`;

  switch (block.type) {
    case 'heading': {
      const content = renderInline(block.text, key);
      if (block.level === 1) {
        return (
          <h1 key={key} className={styles.heading1}>
            {content}
          </h1>
        );
      }
      if (block.level === 2) {
        return (
          <h2 key={key} className={styles.heading2}>
            {content}
          </h2>
        );
      }
      return (
        <h3 key={key} className={styles.heading3}>
          {content}
        </h3>
      );
    }
    case 'list':
      return block.ordered ? (
        <ol key={key} className={styles.list}>
          {block.items.map((item, itemIndex) => (
            <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
          ))}
        </ol>
      ) : (
        <ul key={key} className={styles.list}>
          {block.items.map((item, itemIndex) => (
            <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
          ))}
        </ul>
      );
    case 'table':
      return (
        <div key={key} className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                {block.header.map((cell, cellIndex) => (
                  <th key={`${key}-h-${cellIndex}`}>{renderInline(cell, `${key}-h-${cellIndex}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={`${key}-r-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${key}-r-${rowIndex}-${cellIndex}`}>{renderInline(cell, `${key}-r-${rowIndex}-${cellIndex}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      return (
        <p key={key} className={styles.paragraph}>
          {renderInline(block.text, key)}
        </p>
      );
  }
};

const Markdown = ({ source }: MarkdownProps): JSX.Element => (
  <article className={styles.markdown}>{parseMarkdown(source).map(renderBlock)}</article>
);

export default Markdown;
