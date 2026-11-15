import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { SENSOR_HEX, SENSOR_ORDER, SENSORS } from '../../data/sensors';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import type { DailyAnalytics } from '../../types/analytics';
import type { SensorId } from '../../types/fire';
import { axisTickDates, dayLabel } from '../../utils/dates';
import { formatCount } from '../../utils/formatters';
import { ChartTooltip } from './ChartTooltip';
import shared from '../../styles/shared.module.css';
import styles from './charts.module.css';

const DATA_KEY: Record<SensorId, keyof DailyAnalytics> = {
  modis: 'modisDetections',
  viirs: 'viirsDetections',
  harmonized: 'harmonizedDetections',
};

/** One line per selected sensor; deselected sensors are hidden. */
export function DetectionComparisonChart({ daily, sensors }: { daily: DailyAnalytics[]; sensors: SensorId[] }) {
  const reduced = usePrefersReducedMotion();
  const ticks = axisTickDates(daily.map((d) => d.date));
  const active = SENSOR_ORDER.filter((s) => sensors.includes(s));

  return (
    <section className={`${shared.card} ${styles.card}`} aria-labelledby="detection-chart-title">
      <div className={styles.header}>
        <h2 id="detection-chart-title" className={styles.title}>
          Detection Count Comparison
        </h2>
        <ul className={styles.legend} aria-label="Legend">
          {active.map((sensor) => (
            <li key={sensor}>
              <span className={styles.legendLine} style={{ background: SENSOR_HEX[sensor], color: SENSOR_HEX[sensor] }} aria-hidden="true" />
              {SENSORS[sensor].label}
            </li>
          ))}
        </ul>
      </div>
      <div
        className={styles.plot}
        role="img"
        aria-label={`Line chart of daily fire detections for ${active.map((s) => SENSORS[s].label).join(' and ')}. Values are listed in the data table below the charts.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={daily} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
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
              label={{ value: 'Number of Detections', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: '#5F6B78', textAnchor: 'middle' } }}
            />
            <Tooltip content={<ChartTooltip unit="detections" />} />
            {active.map((sensor) => (
              <Line
                key={sensor}
                dataKey={DATA_KEY[sensor]}
                name={SENSORS[sensor].label}
                type="linear"
                stroke={SENSOR_HEX[sensor]}
                strokeWidth={2}
                dot={{ r: 3, fill: '#FFFFFF', stroke: SENSOR_HEX[sensor], strokeWidth: 1.5 }}
                activeDot={{ r: 5 }}
                isAnimationActive={!reduced}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
