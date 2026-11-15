import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import chartStyles from '../components/charts/charts.module.css';
import { ErrorState, LoadingState } from '../components/shared/States';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { useServiceQuery } from '../hooks/useServiceQuery';
import {
  cellSummary,
  fetchModelPreview,
  hourlyMeanProbability,
  type ModelPreviewData,
} from '../services/modelPreviewService';
import shared from '../styles/shared.module.css';
import styles from './ModelPreviewPage.module.css';

const ORANGE = '#EC7D28';

function formatUtcHour(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export function ModelPreviewPage() {
  const query = useServiceQuery<ModelPreviewData>('model-preview', fetchModelPreview);
  const reduced = usePrefersReducedMotion();
  const data = query.data;

  if (!data) {
    return (
      <main className={shared.page}>
        <h1 className="visually-hidden">Model Preview</h1>
        {query.status === 'error' ? (
          <ErrorState message={query.error ?? 'Unknown error.'} onRetry={query.retry} />
        ) : (
          <LoadingState label="Loading model preview…" />
        )}
      </main>
    );
  }

  const { metadata, items, validation } = data;
  const hourly = hourlyMeanProbability(items);
  const cells = cellSummary(items);
  const { n, positives, negatives } = validation.comparison;

  return (
    <main className={shared.page}>
      <h1 className="visually-hidden">Model Preview</h1>

      <section className={styles.notice} role="note" aria-label="Exploratory preview">
        <p className={styles.noticeLabel}>Exploratory preview</p>
        <p className={styles.noticeText}>{metadata.disclaimer}</p>
      </section>

      <section className={styles.facts} aria-label="Model preview facts">
        <article className={`${shared.card} ${styles.factCard}`}>
          <h2 className={styles.factTitle}>Grid cells</h2>
          <p className={styles.factValue}>{metadata.cells}</p>
        </article>
        <article className={`${shared.card} ${styles.factCard}`}>
          <h2 className={styles.factTitle}>Time range</h2>
          <p className={styles.factValue}>
            {formatUtcHour(metadata.start_utc)} to {formatUtcHour(metadata.last_bin_utc)}
          </p>
        </article>
        <article className={`${shared.card} ${styles.factCard}`}>
          <h2 className={styles.factTitle}>Training observations</h2>
          <p className={styles.factValue}>
            {metadata.training_observations.modis} MODIS and {metadata.training_observations.viirs} VIIRS
          </p>
        </article>
        <article className={`${shared.card} ${styles.factCard}`}>
          <h2 className={styles.factTitle}>Source granules</h2>
          <p className={styles.factValue}>{metadata.source_granules.length}</p>
        </article>
      </section>

      <section className={`${shared.card} ${chartStyles.card}`} aria-labelledby="model-prob-chart-title">
        <div className={chartStyles.header}>
          <h2 id="model-prob-chart-title" className={chartStyles.title}>
            Model-estimated fire probability (mean over cells, hourly)
          </h2>
        </div>
        <div
          className={chartStyles.plot}
          role="img"
          aria-label="Line chart of hourly model-estimated fire probability averaged over grid cells."
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={hourly} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid vertical={false} stroke="#E6E8EC" />
              <XAxis
                dataKey="time"
                tickFormatter={(v: string) => v.slice(5, 16).replace('T', ' ')}
                tickLine={false}
                axisLine={{ stroke: '#C9CED6' }}
                tick={{ fontSize: 12, fill: '#5F6B78' }}
                minTickGap={36}
              />
              <YAxis
                domain={[0, 1]}
                width={52}
                tickFormatter={(v: number) => v.toFixed(2)}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12, fill: '#5F6B78' }}
              />
              <Tooltip
                labelFormatter={(label) => formatUtcHour(String(label))}
                formatter={(value) => [Number(value).toFixed(3), 'Mean probability']}
              />
              <Line
                dataKey="meanPFire"
                name="Mean probability"
                type="linear"
                stroke={ORANGE}
                strokeWidth={2}
                dot={false}
                isAnimationActive={!reduced}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className={`${shared.card} ${styles.section}`} aria-labelledby="cell-summary-heading">
        <h2 id="cell-summary-heading" className={styles.sectionTitle}>
          Cell summary
        </h2>
        <div className={shared.tableScroll}>
          <table className={shared.table}>
            <thead>
              <tr>
                <th scope="col">Cell</th>
                <th scope="col">Latitude</th>
                <th scope="col">Longitude</th>
                <th scope="col">Mean probability</th>
                <th scope="col">Max probability</th>
                <th scope="col">Observed bins</th>
              </tr>
            </thead>
            <tbody>
              {cells.map((row) => (
                <tr key={row.cell_id}>
                  <th scope="row">{row.cell_id}</th>
                  <td>{row.latitude.toFixed(3)}</td>
                  <td>{row.longitude.toFixed(3)}</td>
                  <td>{row.meanPFire.toFixed(3)}</td>
                  <td>{row.maxPFire.toFixed(3)}</td>
                  <td>{row.observedBins}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={`${shared.card} ${styles.section}`} aria-labelledby="validation-heading">
        <h2 id="validation-heading" className={styles.sectionTitle}>
          Validation
        </h2>
        <p className={styles.validationText}>
          Held-out observations: {n} ({positives} positives, {negatives} negatives). Held-out scores measure detection
          agreement only. With no positive cases in the holdout, skill at finding fires cannot be assessed yet.
        </p>
      </section>
    </main>
  );
}
