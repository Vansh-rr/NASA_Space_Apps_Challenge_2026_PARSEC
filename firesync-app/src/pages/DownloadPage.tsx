import { useMemo, useState } from 'react';

import {
  Activity,
  CalendarDays,
  ChartColumnIncreasing,
  Download,
  FileSpreadsheet
} from 'lucide-react';

import {
  CartesianGrid,
  ComposedChart,
  Bar,
  Line,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';

import { ErrorState, LoadingState } from '../components/shared/States';
import { DATA_YEARS } from '../data/dataYears';
import { REGIONS } from '../data/regions';
import { fetchDownloadData } from '../services/downloadService';
import { useServiceQuery } from '../hooks/useServiceQuery';
import {
  EXPLORE_REGION,
  EXPLORE_SENSORS,
  type ExploreSensor,
  IS_DEMO_DATA,
  fetchExploreObservations
} from '../services/fireData';
import type { FireObservation } from '../types/fire';

import {
  downloadBurningCalendar,
  downloadFireAnalytics,
  downloadFireHistory,
  downloadFireObservations
} from '../utils/downloadCsv';

import {
  summarizeFireAnalytics
} from '../utils/fireDownloadAnalytics';

import shared from '../styles/shared.module.css';
import styles from './DownloadPage.module.css';

const MIN_DATE = `${Math.min(...DATA_YEARS)}-01-01`;
const MAX_DATE = `${Math.max(...DATA_YEARS)}-12-31`;
/** Observations are fetched one month at a time, so very long ranges are capped. */
const MAX_EXPORT_MONTHS = 12;
const MAX_POINTS_PER_MONTH = 50000;

export function DownloadPage() {
  const [startDate, setStartDate] =
    useState('2023-01-01');

  const [endDate, setEndDate] =
    useState('2023-12-31');

  const [region, setRegion] = useState(EXPLORE_REGION);
  const [sensor, setSensor] = useState<ExploreSensor>('MODIS');

  const [showChart, setShowChart] =
    useState(true);

  const [exporting, setExporting] =
    useState(false);

  const [exportError, setExportError] =
    useState<string | null>(null);

  const isValidDateRange = Boolean(
    startDate &&
    endDate &&
    startDate >= MIN_DATE &&
    endDate <= MAX_DATE &&
    startDate <= endDate
  );

  // Load real monthly counts and official historical anomalies.
  const activity = useServiceQuery(
    `download-${region}-${sensor}`,
    signal => fetchDownloadData(region, sensor, signal)
  );

  const cells = useMemo(() => activity.data?.cells ?? [], [activity.data]);
  const allCalendarRows = useMemo(() => activity.data?.calendar ?? [], [activity.data]);

  const inRange = (year: number, month: number) => {
    const first = `${year}-${String(month).padStart(2, '0')}-01`;
    const last = new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
    return first <= endDate && last >= startDate;
  };

  const filteredCells = isValidDateRange ? cells.filter(cell => inRange(cell.year, cell.month)) : [];
  const calendarRows = isValidDateRange ? allCalendarRows.filter(row => inRange(row.year, row.month)) : [];
  const exportMonths = filteredCells.filter(cell => cell.value > 0).sort((a, b) => a.year - b.year || a.month - b.month);
  const detectionsInMonths = exportMonths.reduce((sum, cell) => sum + cell.value, 0);
  const tooManyMonths = exportMonths.length > MAX_EXPORT_MONTHS;
  const hasCappedMonth = exportMonths.some(cell => cell.value > MAX_POINTS_PER_MONTH);
  const canDownload = isValidDateRange && activity.status === 'ready' && calendarRows.length > 0;

  // Analytics summary
  const analytics = useMemo(
    () => summarizeFireAnalytics(calendarRows),
    [calendarRows]
  );

  const suffix = `${startDate}_to_${endDate}`;

  // Fetch the detections month by month, then trim to the exact dates
  async function handleObservationsDownload() {
    setExporting(true);
    setExportError(null);

    try {
      const collected: FireObservation[] = [];

      for (const cell of exportMonths) {
        const rows = await fetchExploreObservations(region, { year: cell.year, month: cell.month }, sensor);

        collected.push(...rows);
      }

      const inRange = collected.filter(fire => {
        const date = fire.observedAt.slice(0, 10);
        return date >= startDate && date <= endDate;
      });

      if (!inRange.length) {
        setExportError(
          'No detections were found for the selected dates.'
        );
        return;
      }

      downloadFireObservations(
        inRange,
        `firesync_observations_${suffix}.csv`
      );
    } catch (err) {
      setExportError(
        err instanceof Error
          ? err.message
          : 'The observations could not be downloaded.'
      );
    } finally {
      setExporting(false);
    }
  }

  if (activity.status === 'error') {
    return (
      <main className={shared.page}>
        <div className={styles.container}>
          <ErrorState
            message={`${activity.error ?? 'Cannot fetch fire data.'} Make sure FastAPI is running at http://localhost:8000 and its database is available.`}
            onRetry={activity.retry}
          />
        </div>
      </main>
    );
  }

  if (activity.status !== 'ready') {
    return (
      <main className={shared.page}>
        <div className={styles.container}>
          <LoadingState label="Loading fire data…" />
        </div>
      </main>
    );
  }

  return (
    <main className={shared.page}>
      <div className={styles.container}>

        {/* PAGE HEADER */}
        <header className={styles.heading}>
          <div className={styles.headingIcon}>
            <Download size={28} />
          </div>

          <div>
            <h1>Download Fire Data</h1>
            <p>
              Export fire observations, historical activity,
              fire analytics, and the burning calendar as CSV files.
            </p>
          </div>
        </header>

        {/* DATE FILTER */}
        <section className={styles.filterCard}>
          <div className={styles.sectionTitle}>
            <CalendarDays size={20} />
            <h2>Select Data Period</h2>
          </div>

          <p className={styles.helperText}>
            Choose the date range for CSV exports and analytics.
          </p>

          <div className={styles.dateRange}>
            <div className={styles.dateField}>
              <label htmlFor="download-region">Region</label>
              <select id="download-region" className={styles.dateInput} value={region} onChange={e => setRegion(e.target.value)}>
                {REGIONS.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div className={styles.dateField}>
              <label htmlFor="download-sensor">Sensor</label>
              <select id="download-sensor" className={styles.dateInput} value={sensor} onChange={e => setSensor(e.target.value as ExploreSensor)}>
                {EXPLORE_SENSORS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
            <div className={styles.dateField}>
              <label htmlFor="start-date">
                Start Date
              </label>

              <input
                id="start-date"
                type="date"
                className={styles.dateInput}
                value={startDate}
                min={MIN_DATE}
                max={MAX_DATE}
                onChange={e =>
                  setStartDate(e.target.value)
                }
              />
            </div>

            <div className={styles.dateField}>
              <label htmlFor="end-date">
                End Date
              </label>

              <input
                id="end-date"
                type="date"
                className={styles.dateInput}
                value={endDate}
                min={MIN_DATE}
                max={MAX_DATE}
                onChange={e =>
                  setEndDate(e.target.value)
                }
              />
            </div>
          </div>

          {!isValidDateRange && (
            <p className={styles.error} role="alert">
              Please select a valid date range between
              {' '}{MIN_DATE} and {MAX_DATE}.
            </p>
          )}

          <div className={styles.selectedPeriod}>
            <CalendarDays size={18} />
            <span>
              Selected Period:{' '}
              <strong>
                {startDate || '—'} to {endDate || '—'}
              </strong>
            </span>
          </div>
        </section>

        {/* DOWNLOAD CARDS */}
        <div className={styles.grid}>

          {/* FIRE OBSERVATIONS */}
          <section className={styles.downloadCard}>
            <div className={styles.fileIcon}>
              <FileSpreadsheet size={26} />
            </div>

            <h2>Fire Observations</h2>

            <p>
              Download sampled {sensor} fire detections for the selected region including
              coordinates, timestamps, satellite sensor and FRP.
            </p>

            <div className={styles.info}>
              <div>
                <span>Format</span>
                <strong>CSV</strong>
              </div>

              <div>
                <span>Detections in months</span>
                <strong>
                  {detectionsInMonths.toLocaleString()}
                </strong>
              </div>
            </div>

            <button
              type="button"
              className={styles.downloadButton}
              disabled={
                !isValidDateRange ||
                !exportMonths.length ||
                tooManyMonths ||
                hasCappedMonth ||
                exporting
              }
              onClick={handleObservationsDownload}
            >
              <Download size={18} />
              {exporting
                ? 'Preparing CSV…'
                : 'Download Observations CSV'}
            </button>

            {tooManyMonths && (
              <p className={styles.error} role="alert">
                Observation exports are limited to
                {' '}{MAX_EXPORT_MONTHS} months with data.
                Please choose a shorter period.
              </p>
            )}

            {hasCappedMonth && (
              <p className={styles.error}>One or more months exceed the API limit of {MAX_POINTS_PER_MONTH.toLocaleString()} observations. Full observation export needs a streaming backend endpoint.</p>
            )}

            {exportError && (
              <p className={styles.error} role="alert">
                {exportError}
              </p>
            )}
          </section>

          {/* FIRE HISTORY */}
          <section className={styles.downloadCard}>
            <div className={styles.fileIcon}>
              <CalendarDays size={26} />
            </div>

            <h2>Fire Activity History</h2>

            <p>
              Export monthly {sensor} detection counts used by
              the Explore fire activity heatmap.
            </p>

            <div className={styles.info}>
              <div>
                <span>Format</span>
                <strong>CSV</strong>
              </div>

              <div>
                <span>Months</span>
                <strong>
                  {filteredCells.length}
                </strong>
              </div>
            </div>

            <button
              type="button"
              className={styles.downloadButton}
              disabled={!canDownload}
              onClick={() =>
                downloadFireHistory(
                  filteredCells,
                  `firesync_history_${suffix}.csv`,
                  IS_DEMO_DATA
                )
              }
            >
              <Download size={18} />
              Download History CSV
            </button>
          </section>

          {/* FIRE ANALYTICS */}
          <section className={styles.downloadCard}>
            <div className={styles.fileIcon}>
              <ChartColumnIncreasing size={26} />
            </div>

            <h2>Fire Analytics (Statistics &amp; Anomalies)</h2>

            <p>
              Export monthly counts, official historical median, anomaly z-scores, percentiles and classifications.
            </p>

            <div className={styles.info}>
              <div>
                <span>Total Detections</span>
                <strong>
                  {analytics.total.toLocaleString()}
                </strong>
              </div>

              <div>
                <span>Anomalous Months</span>
                <strong>
                  {analytics.anomalies}
                </strong>
              </div>
            </div>

            <button
              type="button"
              className={styles.downloadButton}
              disabled={!canDownload}
              onClick={() =>
                downloadFireAnalytics(
                  calendarRows,
                  `firesync_fire_analytics_${suffix}.csv`,
                  IS_DEMO_DATA
                )
              }
            >
              <Download size={18} />
              Download Analytics CSV
            </button>
          </section>

          {/* BURNING CALENDAR */}
          <section className={styles.downloadCard}>
            <div className={styles.fileIcon}>
              <CalendarDays size={26} />
            </div>

            <h2>Burning Activity Calendar</h2>

            <p>
              Export year-by-month fire activity with detection counts, historical percentiles, activity categories and coverage status.
            </p>

            <div className={styles.info}>
              <div>
                <span>Format</span>
                <strong>CSV</strong>
              </div>

              <div>
                <span>Calendar Months</span>
                <strong>
                  {calendarRows.length}
                </strong>
              </div>
            </div>

            <button
              type="button"
              className={styles.downloadButton}
              disabled={!canDownload}
              onClick={() =>
                downloadBurningCalendar(
                  calendarRows,
                  `firesync_burning_calendar_${suffix}.csv`,
                  IS_DEMO_DATA
                )
              }
            >
              <Download size={18} />
              Download Calendar CSV
            </button>
          </section>

        </div>

        {/* FIRE ANALYTICS PREVIEW */}
        <section className={styles.previewCard}>
          <div className={styles.previewHeading}>
            <div className={styles.sectionTitle}>
              <Activity size={20} />
              <h2>Fire Analytics Preview</h2>
            </div>

            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() =>
                setShowChart(value => !value)
              }
              aria-expanded={showChart}
            >
              {showChart ? 'Hide Graph' : 'Show Graph'}
            </button>
          </div>

          {/* STATISTICS */}
          {!activity.data?.historyAvailable && (
            <p className={styles.error}>Historical anomaly data is unavailable from /history. Count exports remain available; anomaly columns will be blank.</p>
          )}
          <div className={styles.metrics}>
            <div>
              <span>Monthly Average</span>
              <strong>
                {analytics.monthlyAverage.toLocaleString()}
              </strong>
            </div>

            <div>
              <span>Peak Month</span>
              <strong>{analytics.peakPeriod}</strong>
            </div>

            <div>
              <span>Peak Detections</span>
              <strong>
                {analytics.peakDetections.toLocaleString()}
              </strong>
            </div>

            <div>
              <span>Anomalies (|z| ≥ 2)</span>
              <strong>{analytics.anomalies}</strong>
            </div>
          </div>

          {/* FIRE GRAPH */}
          {showChart && (
            calendarRows.length ? (
              <>
                <p className={styles.chartHint}>
                  Bars show monthly detections (left axis).
                  The blue line shows anomaly z-scores
                  (right axis). Hover for details.
                </p>

                <div className={styles.chartWrap}>
                  <ResponsiveContainer
                    width="100%"
                    height="100%"
                  >
                    <ComposedChart
                      data={calendarRows}
                      margin={{
                        top: 12,
                        right: 12,
                        left: 2,
                        bottom: 8
                      }}
                    >
                      <CartesianGrid
                        stroke="#e2e8f0"
                        strokeDasharray="4 4"
                      />

                      <XAxis
                        dataKey="period"
                        tick={{ fontSize: 11 }}
                        minTickGap={25}
                      />

                      <YAxis
                        yAxisId="detections"
                        tick={{ fontSize: 11 }}
                        width={58}
                      />

                      <YAxis
                        yAxisId="anomaly"
                        orientation="right"
                        tick={{ fontSize: 11 }}
                        width={40}
                      />

                      <Tooltip
                        formatter={(value, name) => [
                          typeof value === 'number'
                            ? value.toLocaleString()
                            : value,
                          name
                        ]}
                      />

                      <Legend />

                      <ReferenceLine
                        yAxisId="anomaly"
                        y={2}
                        stroke="#dc2626"
                        strokeDasharray="5 5"
                      />

                      <ReferenceLine
                        yAxisId="anomaly"
                        y={-2}
                        stroke="#dc2626"
                        strokeDasharray="5 5"
                      />

                      <Bar
                        yAxisId="detections"
                        dataKey="value"
                        name="Fire Detections"
                        fill="#ed7135"
                        radius={[4, 4, 0, 0]}
                        maxBarSize={38}
                      />

                      <Line
                        yAxisId="anomaly"
                        type="monotone"
                        dataKey="anomalyZScore"
                        name="Anomaly Z-Score"
                        stroke="#2563eb"
                        strokeWidth={2.5}
                        dot={calendarRows.length <= 24}
                        connectNulls={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <p className={styles.empty}>
                Choose a valid period to view the graph.
              </p>
            )
          )}
        </section>

        {/* DATA NOTICE */}
        <div className={styles.notice}>
          <strong>Data Notice</strong>

          <p>
            Data is retrieved from the PARSEC FastAPI service for the selected
            region and sensor. Missing months are not assumed to contain zero fires.
            The Download page requires the Python API and its DuckDB database to be running.
            The observation export is limited to {MAX_EXPORT_MONTHS} months and
            {MAX_POINTS_PER_MONTH.toLocaleString()} points per month to avoid partial CSVs.
          </p>
          <p>
            Monthly calendar and analytics exports include the entire month if it
            overlaps the selected date range. Anomaly metrics use the official
            /history endpoint; missing history stays unavailable instead of being estimated.
          </p>
        </div>

      </div>
    </main>
  );
}
