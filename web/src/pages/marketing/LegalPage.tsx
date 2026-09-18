// 法务类静态页面的统一版式，由服务条款与隐私政策页复用。

import type { ReactNode } from 'react';

import styles from './LegalPage.module.less';

export interface LegalSection {
  heading: string;
  paragraphs: string[];
  list?: string[];
}

interface LegalPageProps {
  title: string;
  updatedAt: string;
  intro: string;
  sections: LegalSection[];
  footer?: ReactNode;
}

const LegalPage = ({ title, updatedAt, intro, sections, footer }: LegalPageProps): JSX.Element => (
  <article className={styles.page}>
    <header className={styles.header}>
      <h1 className={styles.title}>{title}</h1>
      <p className={styles.updatedAt}>最后更新：{updatedAt}</p>
      <p className={styles.intro}>{intro}</p>
    </header>

    <div className={styles.sections}>
      {sections.map((section, index) => (
        <section key={section.heading} className={styles.section}>
          <h2 className={styles.heading}>
            <span className={styles.index}>{index + 1}</span>
            {section.heading}
          </h2>

          {section.paragraphs.map((paragraph) => (
            <p key={paragraph} className={styles.paragraph}>
              {paragraph}
            </p>
          ))}

          {section.list === undefined ? null : (
            <ul className={styles.list}>
              {section.list.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>

    {footer === undefined ? null : <footer className={styles.footer}>{footer}</footer>}
  </article>
);

export default LegalPage;
