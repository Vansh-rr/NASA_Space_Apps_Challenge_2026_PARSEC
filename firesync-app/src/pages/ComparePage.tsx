import { useCallback, useRef, useState } from 'react';
import { ComparisonDataTable } from '../components/compare/ComparisonDataTable';
import { ComparisonToolbar } from '../components/compare/ComparisonToolbar';
import { SectionHeading } from '../components/compare/SectionHeading';
import { SensorMapCard } from '../components/compare/SensorMapCard';
import { SensorTrendCard } from '../components/compare/SensorTrendCard';
import { ErrorState, LoadingState } from '../components/shared/States';
import { REFERENCE_MONTH, REFERENCE_REGION } from '../data/demoModel';
import { getRegion } from '../data/regions';
import { useComparisonData } from '../hooks/useComparisonData';
import { useSyncedMapCamera } from '../hooks/useSyncedMapCamera';
import type { ComparisonFilters } from '../types/comparison';
import type { SensorId } from '../types/fire';
import { peakSummary, sharedTicks } from '../utils/comparison';
import { monthRangeLabel } from '../utils/dates';
import shared from '../styles/shared.module.css';
import styles from './ComparePage.module.css';

const INITIAL: ComparisonFilters = { regionId: REFERENCE_REGION, month: REFERENCE_MONTH, focusedSensor: 'harmonized' };

export function ComparePage() {
  const [filters, setFilters] = useState<ComparisonFilters>(INITIAL);
  const query = useComparisonData(filters.regionId, filters.month);
  const sync = useSyncedMapCamera();
  const cardRefs = useRef<Partial<Record<SensorId, HTMLElement | null>>>({});
  const data = query.data;
  const region = getRegion(data?.regionId ?? filters.regionId);
  const focused = filters.focusedSensor;

  // Focus is presentation state: it never changes which records are loaded or shown.
  const focusSensor = useCallback((sensor: SensorId) => {
    setFilters((f) => ({ ...f, focusedSensor: sensor }));
    if (window.matchMedia('(max-width: 767px)').matches) {
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      cardRefs.current[sensor]?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    }
  }, []);

  return (
    <>
      <ComparisonToolbar
        filters={filters}
        isDemo={data?.isDemo ?? true}
        updatedAt={data?.updatedAt ?? null}
        isUpdating={query.isUpdating}
        onChange={setFilters}
        onFocusSensor={focusSensor}
      />

      <main className={shared.page}>
        <h1 className="visually-hidden">Compare satellite fire records</h1>

        {!data ? (
          query.status === 'error' ? (
            <ErrorState message={query.error ?? 'Unknown error.'} onRetry={query.retry} />
          ) : (
            <LoadingState label="Loading comparison…" />
          )
        ) : (
          <>
            {query.status === 'error' && (
              <p role="alert" className={styles.stale}>
                The latest request failed; earlier results are shown.{' '}
                <button type="button" className={styles.linkButton} onClick={query.retry}>
                  Try again
                </button>
              </p>
            )}

            <section aria-labelledby="sensor-comparison-heading" className={styles.section}>
              <SectionHeading
                id="sensor-comparison-heading"
                eyebrow="Side-by-side analysis"
                title="Sensor Comparison"
                description="Compare detection density, intensity, and active days across each satellite product."
              />
              <div className={styles.grid}>
                <div className={styles.stack}>
                  {(['modis', 'viirs'] as const).map((sensor) => (
                    <SensorMapCard
                      key={sensor}
                      ref={(el) => {
                        cardRefs.current[sensor] = el;
                      }}
                      record={data.records[sensor]}
                      bounds={region.bounds}
                      cities={region.cities.slice(0, 4)}
                      sync={sync}
                      isDemo={data.isDemo}
                      focused={focused === sensor}
                    />
                  ))}
                </div>
                <SensorMapCard
                  ref={(el) => {
                    cardRefs.current.harmonized = el;
                  }}
                  record={data.records.harmonized}
                  bounds={region.bounds}
                  cities={region.cities}
                  sync={sync}
                  isDemo={data.isDemo}
                  focused={focused === 'harmonized'}
                  large
                />
              </div>
            </section>

            <section aria-labelledby="detection-trends-heading" className={`${styles.section} ${styles.trends}`}>
              <SectionHeading
                id="detection-trends-heading"
                eyebrow={monthRangeLabel(data.month)}
                title="Detection Trends"
                description={peakSummary(data)}
              />
              <div className={styles.grid}>
                <div className={styles.stack}>
                  {(['modis', 'viirs'] as const).map((sensor) => (
                    <SensorTrendCard
                      key={sensor}
                      record={data.records[sensor]}
                      month={data.month}
                      yTicks={sharedTicks(data)}
                      focused={focused === sensor}
                    />
                  ))}
                </div>
                <SensorTrendCard
                  record={data.records.harmonized}
                  month={data.month}
                  yTicks={sharedTicks(data)}
                  focused={focused === 'harmonized'}
                  large
                />
              </div>
              <ComparisonDataTable data={data} />
            </section>

            <p className={shared.methodology}>
              <strong>How to read this comparison:</strong> {data.methodology}
            </p>
          </>
        )}
      </main>
    </>
  );
}
