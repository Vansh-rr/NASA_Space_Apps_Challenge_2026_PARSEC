import { Area, AreaChart, CartesianGrid, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { SENSOR_HEX, SENSORS } from '../../data/sensors';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import type { SensorComparison } from '../../types/comparison';
import { axisTickDates, dayLabel, monthLabel } from '../../utils/dates';
import { formatCompact, formatCount } from '../../utils/formatters';
import { peakDates } from '../../utils/metrics';
import { ChartTooltip } from '../charts/ChartTooltip';
import styles from '../../pages/ComparePage.module.css';

interface Props {
  record: SensorComparison;
  month: string;
  /** Shared across the three charts so heights can be compared fairly. */
  yTicks: number[];
  focused: boolean;
  large?: boolean;
}

/** Navy pill above the peak point. Derived from the data, not a fixed label. */
function PeakLabel({ viewBox, text }: { viewBox?: { x?: number; y?: number; width?: number }; text: string }) {
  if (!viewBox || viewBox.x === undefined || viewBox.y === undefined) return null;
  const cx = viewBox.x + (viewBox.width ?? 0) / 2;
  const width = text.length * 7 + 18;
  return (
    <g>
      <rect x={cx - width / 2} y={viewBox.y - 32} width={width} height={22} rx={6} fill="#101E2D" />
      <text x={cx} y={viewBox.y - 17} textAnchor="middle" fill="#FFFFFF" fontSize={11.5} fontWeight={700}>
        {text}
      </text>
    </g>
  );
}

export function SensorTrendCard({ record, month, yTicks, focused, large }: Props) {
  const reduced = usePrefersReducedMotion();
  const config = SENSORS[record.sensor];
  const color = SENSOR_HEX[record.sensor];
  const data = record.dailyCounts;
  const ticks = axisTickDates(data.map((d) => d.date), 7);
  const peaks = peakDates(data);
  const peakDate = peaks[0];
  const peakValue = peakDate ? data.find((d) => d.date === peakDate)?.count ?? null : null;
  const hasData = data.some((d) => d.count !== null && d.count > 0);
  const titleId = `trend-${record.sensor}`;

  return (
    <article
      className={`${styles.card} ${styles.trendCard} ${large ? styles.cardLarge : ''} ${focused ? styles.cardFocused : ''}`}
      style={{ '--accent': config.color, '--tint': config.tint } as React.CSSProperties}
      aria-labelledby={titleId}
    >
      <header className={styles.trendHeader}>
        <div>
          <p className={styles.trendBadge}>
            <span aria-hidden="true" />
            {config.label}
          </p>
          <h3 id={titleId} className={styles.trendTitle}>
            {config.label} Detections
          </h3>
          <p className={styles.cardSubtitle}>Daily fire detection count · {monthLabel(month)}</p>
        </div>
        <div className={styles.trendTotal}>
          <p>Monthly total</p>
          <p className={styles.trendTotalValue}>{formatCount(record.detectionCount)}</p>
        </div>
      </header>

      <div className={styles.trendPlot}>
        {hasData ? (
          <div
            className={styles.trendPlotInner}
            role="img"
            aria-label={`Area chart of daily ${config.label} detections${peakDate ? `, peaking at ${formatCount(peakValue)} on ${dayLabel(peakDate)}` : ''}. Values are in the data table below.`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 40, right: 16, bottom: 4, left: 4 }}>
                <defs>
                  <linearGradient id={`fill-${record.sensor}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#E6E8EC" strokeDasharray="0" vertical={false} />
                <XAxis
                  dataKey="date"
                  ticks={ticks}
                  tickFormatter={dayLabel}
                  tickLine={false}
                  axisLine={{ stroke: '#C9CED6' }}
                  tick={{ fontSize: 12, fill: '#5F6B78' }}
                />
                <YAxis
                  width={58}
                  domain={[0, yTicks[yTicks.length - 1]]}
                  ticks={yTicks}
                  tickFormatter={formatCompact}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 12, fill: '#5F6B78' }}
                  label={{ value: 'Detections', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: '#5F6B78', textAnchor: 'middle' } }}
                />
                <Tooltip content={<ChartTooltip unit="detections" />} />
                <Area
                  dataKey="count"
                  name={config.label}
                  type="linear"
                  stroke={color}
                  strokeWidth={large ? 2.5 : 2}
                  fill={`url(#fill-${record.sensor})`}
                  dot={{ r: large ? 3.5 : 2.5, fill: '#FFFFFF', stroke: color, strokeWidth: 1.5 }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={!reduced}
                />
                {peakDate && peakValue !== null && (
                  <ReferenceDot
                    x={peakDate}
                    y={peakValue}
                    r={large ? 6 : 5}
                    fill={color}
                    stroke="#FFFFFF"
                    strokeWidth={2}
                    label={(props: { viewBox?: { x?: number; y?: number; width?: number } }) => (
                      <PeakLabel viewBox={props.viewBox} text={peaks.length > 1 ? `${dayLabel(peakDate)} +${peaks.length - 1}` : dayLabel(peakDate)} />
                    )}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className={styles.trendEmpty}>No detections recorded for this month.</p>
        )}
      </div>
    </article>
  );
}
