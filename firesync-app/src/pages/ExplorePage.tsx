import { useCallback, useState } from 'react';
import { ActivityHeatmap } from '../components/activity/ActivityHeatmap';
import { ActivityLegend } from '../components/activity/ActivityLegend';
import { FireMap } from '../components/map/FireMap';
import { SearchPanel } from '../components/search/SearchPanel';
import { ErrorState, LoadingState } from '../components/shared/States';
import { REGIONS } from '../data/regions';
import { useExploreFilters } from '../hooks/useExploreFilters';
import { useLocationSearch } from '../hooks/useLocationSearch';
import { useServiceQuery } from '../hooks/useServiceQuery';
import {
  DEFAULT_PERIOD,
  EXPLORE_REGION,
  EXPLORE_SENSORS,
  type ExploreSensor,
  activityUnit,
  fetchActivityMatrix,
  fetchExploreObservations,
  insideArea,
} from '../services/fireData';
import type { Bounds, SearchMode } from '../types/fire';
import { MONTH_SHORT, monthLabel, toMonthKey } from '../utils/dates';
import { formatCount } from '../utils/formatters';
import shared from '../styles/shared.module.css';
import styles from './ExplorePage.module.css';

export function ExplorePage() {
  const { filters, setMode, setQuery, setLocation, togglePeriod, clearPeriod } = useExploreFilters();
  const search = useLocationSearch(setLocation);
  const [regionId, setRegionId] = useState(EXPLORE_REGION);
  const [sensor, setSensor] = useState<ExploreSensor>('MODIS');
  const [drawing, setDrawing] = useState(false);
  const [area, setArea] = useState<Bounds | null>(null);
  const unit = activityUnit(sensor);

  const activity = useServiceQuery(`explore-activity-${regionId}-${sensor}`, (signal) => fetchActivityMatrix(regionId, sensor, signal));
  const cells = activity.data ?? [];
  // no month selected: show the default month so the map is never empty
  const shown = filters.selectedPeriod ?? DEFAULT_PERIOD;
  const shownKey = toMonthKey(shown.year, shown.month);
  const points = useServiceQuery(`explore-${regionId}-${sensor}-${shownKey}`, (signal) =>
    fetchExploreObservations(regionId, shown, sensor, signal),
  );
  const observations = points.data ?? [];
  const loadingPoints = points.status === 'loading' || points.isUpdating;
  const region = REGIONS.find((r) => r.id === regionId) ?? REGIONS[0];
  const sensorInfo = EXPLORE_SENSORS.find((s) => s.id === sensor)!;

  const inArea = area ? insideArea(observations, area) : [];
  const areaFrp = inArea.reduce((sum, o) => sum + (o.frpMw ?? 0), 0);

  const changeMode = useCallback(
    (mode: SearchMode) => {
      setMode(mode);
      search.reset();
    },
    [setMode, search],
  );

  const onAreaDrawn = useCallback((drawn: Bounds) => {
    setArea(drawn);
    setDrawing(false);
  }, []);

  const period = filters.selectedPeriod;
  const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => b - a);
  const fmt = (v: number) => v.toFixed(2);

  return (
    <main className={shared.page}>
      <h1 className="visually-hidden">Explore wildfire activity</h1>

      <SearchPanel
        mode={filters.mode}
        query={filters.query}
        loading={search.status === 'loading'}
        error={search.error}
        choices={search.choices}
        location={filters.selectedLocation}
        onModeChange={changeMode}
        onQueryChange={setQuery}
        onSubmit={() => search.search(filters.mode, filters.query)}
        onChoose={search.choose}
        onClearLocation={() => setLocation(null)}
      />

      <div className={styles.periodBar}>
        <label htmlFor="explore-region" className={shared.fieldLabel}>
          Region
        </label>
        <div className={shared.selectWrap}>
          <select
            id="explore-region"
            className={shared.select}
            value={regionId}
            onChange={(e) => {
              setRegionId(e.target.value);
              setArea(null);
            }}
          >
            {REGIONS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <label htmlFor="explore-sensor" className={shared.fieldLabel}>
          Fire record
        </label>
        <div className={shared.selectWrap}>
          <select
            id="explore-sensor"
            className={shared.select}
            value={sensor}
            onChange={(e) => setSensor(e.target.value as ExploreSensor)}
          >
            {EXPLORE_SENSORS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <p>{sensorInfo.note}</p>
      </div>

      <section className={styles.activity} aria-label="Fire activity calendar">
        {activity.status === 'error' && <ErrorState message={activity.error ?? ''} onRetry={activity.retry} />}
        {activity.status === 'loading' && <LoadingState label="Loading fire activity…" />}
        {activity.status === 'ready' && <ActivityHeatmap cells={cells} unit={unit} selected={period} onToggle={togglePeriod} />}
        <ActivityLegend />
      </section>

      <div className={styles.periodBar}>
        <p aria-live="polite">
          {points.status === 'error' ? (
            <>Map data could not be loaded: {points.error}</>
          ) : activity.status === 'ready' && cells.length === 0 ? (
            <>No data downloaded for {region.label} yet. British Columbia has the full 2003–2024 record.</>
          ) : loadingPoints ? (
            <>Loading <strong>{monthLabel(shownKey)}</strong> detections…</>
          ) : period ? (
            <>
              Showing <strong>{monthLabel(shownKey)}</strong>: {formatCount(observations.length)} {sensorInfo.label} detections on the map.{' '}
              <button type="button" className={styles.linkButton} onClick={clearPeriod}>
                Back to July 2023
              </button>
            </>
          ) : (
            <>
              Showing <strong>{monthLabel(shownKey)}</strong>, the record fire season: {formatCount(observations.length)}{' '}
              {sensorInfo.label} detections on the map. Select a month above to see another.
            </>
          )}
        </p>
      </div>

      <div className={styles.periodBar}>
        <button
          type="button"
          className={shared.button}
          aria-pressed={drawing}
          onClick={() => setDrawing((d) => !d)}
        >
          {drawing ? 'Cancel drawing' : area ? 'Draw a new area' : 'Draw area of interest'}
        </button>
        {drawing && <p>Press and drag on the map to draw a rectangle.</p>}
        {!drawing && area && (
          <>
            <p aria-live="polite">
              <strong>{formatCount(inArea.length)}</strong> {sensorInfo.label} detections inside the area in{' '}
              {MONTH_SHORT[shown.month - 1]} {shown.year}, total FRP <strong>{formatCount(Math.round(areaFrp))} MW</strong>{' '}
              (lat {fmt(area[1])} to {fmt(area[3])}, lon {fmt(area[0])} to {fmt(area[2])}).
            </p>
            <button type="button" className={styles.linkButton} onClick={() => setArea(null)}>
              Clear area
            </button>
          </>
        )}
      </div>

      <FireMap
        className={styles.map}
        label={`Wildfire map of ${region.label}`}
        observations={observations}
        bounds={region.bounds}
        cities={region.cities}
        focus={filters.selectedLocation}
        drawing={drawing}
        area={area}
        onAreaDrawn={onAreaDrawn}
      />

      <details className={shared.details}>
        <summary>View activity values as a table</summary>
        <div className={shared.tableScroll}>
          <table className={shared.table}>
            <caption className="visually-hidden">Monthly {unit}</caption>
            <thead>
              <tr>
                <th scope="col">Year</th>
                {MONTH_SHORT.map((m) => (
                  <th key={m} scope="col">
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {years.map((year) => (
                <tr key={year}>
                  <th scope="row">{year}</th>
                  {cells
                    .filter((c) => c.year === year)
                    .sort((a, b) => a.month - b.month)
                    .map((c) => (
                      <td key={c.month}>{formatCount(c.value)}</td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </main>
  );
}
