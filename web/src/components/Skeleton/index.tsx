import styles from './Skeleton.module.less';

interface SkeletonRowsProps {
  /** 骨架行数。 */
  rows?: number;
  /** 列数——与所在表格的列数一致，栅格才能对齐。 */
  cols?: number;
}

/** 表格骨架屏：列表运行中先铺 shimmer 灰条占位，结果逐批到达后原位替换。 */
export default function SkeletonRows({ rows = 5, cols = 8 }: SkeletonRowsProps): JSX.Element {
  return (
    <>
      {Array.from({ length: rows }, (_, rowIndex) => (
        <tr key={rowIndex} aria-hidden className={styles.row}>
          {Array.from({ length: cols }, (_, colIndex) => (
            <td key={colIndex}>
              {/* 第 3 列画成圆角方块（对齐公司头像/角标位），其余按列做宽度错落的灰条 */}
              <div
                className={colIndex === 2 ? styles.mark : styles.bar}
                style={colIndex === 2 ? undefined : { width: `${52 + ((colIndex * 17 + rowIndex * 29) % 38)}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
