import { useState } from 'react';
import { ChartDataTable } from '../components/charts/ChartDataTable';
import { DetectionComparisonChart } from '../components/charts/DetectionComparisonChart';
import { FrpTimeChart } from '../components/charts/FrpTimeChart';
import { AnalyticsFilters } from '../components/filters/AnalyticsFilters';
import { FireMap } from '../components/map/FireMap';
import { MetricsGrid } from '../components/metrics/MetricsGrid';
import { DemoBadge, ErrorState, LoadingState } from '../components/shared/States';
import { getRegion } from '../data/regions';
import { useAnalytics } from '../hooks/useAnalytics';
import type { AnalyticsFilters as Filters } from '../types/analytics';
import { MONTH_SHORT, monthLabel } from '../utils/dates';
import { formatCount } from '../utils/formatters';
import shared from '../styles/shared.module.css';
import styles from './AnalyticsPage.module.css';

const INITIAL: Filters = { regionId: 'british_columbia', month: '2023-07', sensors: ['modis', 'viirs'] };

export function AnalyticsPage() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const query = useAnalytics(filters);
  const data = query.data;
  // While a refresh is in flight the previous response stays on screen, described by its own filters.
  const shown = data?.filters;
  const region = getRegion(shown?.regionId ?? filters.regionId);

  return (
    <main className={shared.page}>
      <h1 className="visually-hidden">Wildfire analytics</h1>

      <AnalyticsFilters filters={filters} onChange={setFilters} />

      {filters.sensors.length === 0 ? (
        <div className={`${shared.card} ${shared.state}`} role="status">
          <p className={shared.stateTitle}>Select at least one sensor</p>
          <p>Choose MODIS, VIIRS or Harmonized above to see metrics, charts and the map.</p>
        </div>
      ) : !data ? (
        query.status === 'error' ? (
          <ErrorState message={query.error ?? 'Unknown error.'} onRetry={query.retry} />
        ) : (
          <LoadingState label="Loading analytics…" />
        )
      ) : (
        <>
          <div className={styles.statusBar}>
            {data.isDemo && <DemoBadge />}
            <p aria-live="polite">
              {region.label} · {monthLabel(data.filters.month)}
              {query.isUpdating && <span className={shared.updating}> · Updating…</span>}
            </p>
            {query.status === 'error' && (
              <p role="alert" className={styles.stale}>
                The latest request failed; earlier results are shown.{' '}
                <button type="button" className={styles.linkButton} onClick={query.retry}>
                  Try again
                </button>
              </p>
            )}
          </div>

          {data.historical && (
            <p className={styles.history}>
              <strong>{monthLabel(data.filters.month)} vs history:</strong> {formatCount(data.historical.value)}{' '}
              {data.historical.sensor} detections, against a median of {formatCount(data.historical.median)} for{' '}
              {MONTH_SHORT[Number(data.filters.month.slice(5, 7)) - 1]} in the other {data.historical.baselineYears} downloaded years
              {' · '}
              <strong>{data.historical.anomalyClass.replaceAll('_', ' ')}</strong>
            </p>
          )}

          <MetricsGrid metrics={data.metrics} />

          <div className={styles.charts}>
            <FrpTimeChart daily={data.daily} />
            <DetectionComparisonChart daily={data.daily} sensors={data.filters.sensors} />
          </div>

          <ChartDataTable daily={data.daily} sensors={data.filters.sensors} />

          <FireMap
            className={styles.map}
            label={`Fire detections map for ${region.label}, ${monthLabel(data.filters.month)}`}
            tone="dark"
            observations={data.observations}
            bounds={region.bounds}
            cities={region.cities}
          />

          <p className={shared.methodology}>
            <strong>How these numbers are produced:</strong> {data.methodology}
          </p>
        </>
      )}
    </main>
  );
}
