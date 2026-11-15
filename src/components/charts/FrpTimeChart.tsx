import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import type { DailyAnalytics } from '../../types/analytics';
import { axisTickDates, dayLabel } from '../../utils/dates';
import { formatCount } from '../../utils/formatters';
import { ChartTooltip } from './ChartTooltip';
import shared from '../../styles/shared.module.css';
import styles from './charts.module.css';

const ORANGE = '#E8701F';
const PEACH = '#FBD5BF';

/** Daily FRP as bars with the 3-day moving-average trend drawn over them. */
export function FrpTimeChart({ daily }: { daily: DailyAnalytics[] }) {
  const reduced = usePrefersReducedMotion();
  const ticks = axisTickDates(daily.map((d) => d.date));

  return (
    <section className={`${shared.card} ${styles.card}`} aria-labelledby="frp-chart-title">
      <div className={styles.header}>
        <h2 id="frp-chart-title" className={styles.title}>
          Fire Radiative Power Over Time
        </h2>
        <ul className={styles.legend} aria-label="Legend">
          <li>
            <span className={styles.legendBar} style={{ background: PEACH }} aria-hidden="true" />
            Daily FRP
          </li>
          <li>
            <span className={styles.legendLine} style={{ background: ORANGE, color: ORANGE }} aria-hidden="true" />
            Trend (3-day average)
          </li>
        </ul>
      </div>
      <div
        className={styles.plot}
        role="img"
        aria-label="Bar and line chart of daily fire radiative power in megawatts. Values are listed in the data table below the charts."
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daily} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
            <CartesianGrid vertical={false} stroke="#E6E8EC" />
            <XAxis
              dataKey="date"
              ticks={ticks}
              tickFormatter={dayLabel}
              tickLine={false}
              axisLine={{ stroke: '#C9CED6' }}
              tick={{ fontSize: 12, fill: '#5F6B78' }}
            />
            <YAxis
              width={64}
              tickFormatter={(v: number) => formatCount(v)}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 12, fill: '#5F6B78' }}
              label={{ value: 'FRP (MW)', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: '#5F6B78', textAnchor: 'middle' } }}
            />
            <Tooltip content={<ChartTooltip unit="MW" />} cursor={{ fill: 'rgba(16, 30, 45, 0.05)' }} />
            <Bar dataKey="dailyFrpMw" name="Daily FRP" fill={PEACH} radius={[3, 3, 0, 0]} isAnimationActive={!reduced} />
            <Line
              dataKey="trendFrpMw"
              name="Trend (3-day average)"
              type="linear"
              stroke={ORANGE}
              strokeWidth={2}
              dot={{ r: 3, fill: '#FFFFFF', stroke: ORANGE, strokeWidth: 1.5 }}
              activeDot={{ r: 5 }}
              isAnimationActive={!reduced}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
