import type { ReactNode } from 'react';
import { Activity, ArrowDown, ArrowUp, Crosshair, Network, Zap } from 'lucide-react';
import type { AnalyticsResponse, Metric } from '../../types/analytics';
import { formatCount, formatOneDecimal, formatSigned, formatTwoDecimals, UNAVAILABLE } from '../../utils/formatters';
import shared from '../../styles/shared.module.css';
import styles from '../../pages/AnalyticsPage.module.css';

function formatValue(metric: Metric): string {
  if (metric.value === null) return UNAVAILABLE;
  if (metric.unit === 'z-score') return formatTwoDecimals(metric.value);
  if (metric.unit === 'MW') return `${formatOneDecimal(metric.value)} MW`;
  return formatCount(metric.value);
}

/** The anomaly delta is an absolute z-score difference; the others are percentages. */
function describeChange(metric: Metric): { text: string; spoken: string; direction: 'up' | 'down' | 'flat' } | null {
  if (metric.change === null) return null;
  const direction = metric.change > 0 ? 'up' : metric.change < 0 ? 'down' : 'flat';
  const text = metric.changeKind === 'percent' ? formatSigned(metric.change, 1, '%') : formatSigned(metric.change, 2);
  const amount = metric.changeKind === 'percent' ? `${Math.abs(metric.change).toFixed(1)} percent` : `${Math.abs(metric.change).toFixed(2)} z-score points`;
  const spoken = direction === 'flat' ? 'no change' : `${direction === 'up' ? 'increase' : 'decrease'} of ${amount}`;
  return { text, spoken, direction };
}

function MetricCard({ title, metric, icon }: { title: string; metric: Metric; icon: ReactNode }) {
  const change = describeChange(metric);
  return (
    <article className={`${shared.card} ${styles.metric}`}>
      <span className={styles.metricIcon} aria-hidden="true">
        {icon}
      </span>
      <div className={styles.metricBody}>
        <h2 className={styles.metricTitle}>{title}</h2>
        <p className={styles.metricValue}>{formatValue(metric)}</p>
        <p className={styles.metricNote}>vs. previous month</p>
      </div>
      {change ? (
        <p className={`${styles.metricChange} ${change.direction === 'down' ? styles.metricDown : ''}`}>
          {change.direction === 'up' && <ArrowUp size={15} aria-hidden="true" />}
          {change.direction === 'down' && <ArrowDown size={15} aria-hidden="true" />}
          <span aria-hidden="true">{change.text}</span>
          <span className="visually-hidden">{change.spoken} versus the previous month</span>
        </p>
      ) : (
        <p className={styles.metricNoChange}>No previous-month baseline</p>
      )}
    </article>
  );
}

export function MetricsGrid({ metrics }: { metrics: AnalyticsResponse['metrics'] }) {
  return (
    <section className={styles.metrics} aria-label="Summary metrics">
      <MetricCard title="Anomaly (z-score)" metric={metrics.anomaly} icon={<Activity size={20} />} />
      <MetricCard title="Total Fire Radiative Power" metric={metrics.totalFrp} icon={<Zap size={20} />} />
      <MetricCard title="Active Fire Detections" metric={metrics.detections} icon={<Crosshair size={20} />} />
      <MetricCard title="Detected Fire Clusters" metric={metrics.clusters} icon={<Network size={20} />} />
    </section>
  );
}
