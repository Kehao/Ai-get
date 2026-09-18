// 折线图：纯 SVG 实现，避免为一张图引入图表库。
// 数据结构与后端 ChartPoint 对齐（每条含 interaction 与 opportunity 两个序列）。

import styles from './LineChart.module.less';

export interface LineChartPoint {
  label: string;
  interaction: number;
  opportunity: number;
}

interface LineChartProps {
  points: LineChartPoint[];
  interactionLabel?: string;
  opportunityLabel?: string;
}

const VIEW_WIDTH = 680;
const VIEW_HEIGHT = 240;
const PADDING = { top: 18, right: 42, bottom: 30, left: 42 };
const Y_TICK_COUNT = 4;

const buildScale = (max: number) => ({
  toY: (value: number): number =>
    VIEW_HEIGHT - PADDING.bottom - (value / max) * (VIEW_HEIGHT - PADDING.top - PADDING.bottom),
  toX: (index: number, count: number): number =>
    PADDING.left + (index / Math.max(1, count - 1)) * (VIEW_WIDTH - PADDING.left - PADDING.right),
});

const toPolyline = (values: number[], toX: (index: number) => number, toY: (value: number) => number): string =>
  values.map((value, index) => `${toX(index).toFixed(1)},${toY(value).toFixed(1)}`).join(' ');

const LineChart = ({
  points,
  interactionLabel = '累计互动客户',
  opportunityLabel = '商机数量',
}: LineChartProps): JSX.Element => {
  const maxValue = Math.max(4, ...points.map((point) => Math.max(point.interaction, point.opportunity)));
  const scale = buildScale(maxValue);
  const toX = (index: number): number => scale.toX(index, points.length);

  const ticks = Array.from({ length: Y_TICK_COUNT + 1 }, (_, index) => Math.round((maxValue / Y_TICK_COUNT) * index));
  const interactionValues = points.map((point) => point.interaction);
  const opportunityValues = points.map((point) => point.opportunity);

  return (
    <div className={styles.wrapper}>
      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span className={styles.dotPrimary} />
          {interactionLabel}
        </span>
        <span className={styles.legendItem}>
          <span className={styles.dotSuccess} />
          {opportunityLabel}
        </span>
      </div>

      <svg className={styles.chart} viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} role="img" aria-label="商机趋势图">
        {ticks.map((tick) => (
          <g key={`tick-${tick}`}>
            <line
              className={styles.grid}
              x1={PADDING.left}
              x2={VIEW_WIDTH - PADDING.right}
              y1={scale.toY(tick)}
              y2={scale.toY(tick)}
            />
            <text className={styles.axisText} x={PADDING.left - 10} y={scale.toY(tick) + 4} textAnchor="end">
              {tick}
            </text>
            <text className={styles.axisText} x={VIEW_WIDTH - PADDING.right + 10} y={scale.toY(tick) + 4}>
              {tick}
            </text>
          </g>
        ))}

        <polyline className={styles.linePrimary} points={toPolyline(interactionValues, toX, scale.toY)} />
        <polyline className={styles.lineSuccess} points={toPolyline(opportunityValues, toX, scale.toY)} />

        {points.map((point, index) => (
          <g key={point.label}>
            <circle className={styles.pointPrimary} cx={toX(index)} cy={scale.toY(point.interaction)} r={3.4} />
            <circle className={styles.pointSuccess} cx={toX(index)} cy={scale.toY(point.opportunity)} r={3.4} />
            <text className={styles.axisText} x={toX(index)} y={VIEW_HEIGHT - 8} textAnchor="middle">
              {point.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
};

export default LineChart;
