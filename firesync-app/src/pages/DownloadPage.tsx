
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

import {
  getActivityMatrix,
  getExploreObservations
} from '../services/fireData';

import {
  downloadBurningCalendar,
  downloadFireAnalytics,
  downloadFireHistory,
  downloadFireObservations
} from '../utils/downloadCsv';

import {
  buildFireCalendarRows,
  summarizeFireAnalytics
} from '../utils/fireDownloadAnalytics';

import shared from '../styles/shared.module.css';
import styles from './DownloadPage.module.css';

const MIN_DATE = '2020-01-01';
const MAX_DATE = '2024-12-31';

export function DownloadPage() {
  const [startDate, setStartDate] =
    useState('2024-01-01');

  const [endDate, setEndDate] =
    useState('2024-12-31');

  const [showChart, setShowChart] =
    useState(true);

  const isValidDateRange = Boolean(
    startDate &&
    endDate &&
    startDate >= MIN_DATE &&
    endDate <= MAX_DATE &&
    startDate <= endDate
  );

  // Retrieve the FireSync activity data
  const { cells } = useMemo(
    () => getActivityMatrix(),
    []
  );

  const allObservations = useMemo(
    () => getExploreObservations(null),
    []
  );

  // Filter observations by date
  const observations = useMemo(
    () =>
      isValidDateRange
        ? allObservations.filter(fire => {
            const date = fire.observedAt.slice(0, 10);

            return (
              date >= startDate &&
              date <= endDate
            );
          })
        : [],
    [
      allObservations,
      isValidDateRange,
      startDate,
      endDate
    ]
  );

  // Filter monthly fire activity
  const filteredCells = useMemo(
    () =>
      isValidDateRange
        ? cells.filter(cell => {
            const monthStart =
              `${cell.year}-${String(cell.month).padStart(2, '0')}-01`;

            const monthEnd = new Date(
              Date.UTC(cell.year, cell.month, 0)
            ).toISOString().slice(0, 10);

            return (
              monthStart <= endDate &&
              monthEnd >= startDate
            );
          })
        : [],
    [cells, startDate, endDate, isValidDateRange]
  );

  // Calculate historical statistics using all years
  const allCalendarRows = useMemo(
    () => buildFireCalendarRows(cells),
    [cells]
  );

  // Then filter the calculated calendar
  const calendarRows = useMemo(() => {
    const keys = new Set(
      filteredCells.map(
        cell =>
          `${cell.year}-${String(cell.month).padStart(2, '0')}`
      )
    );

    return allCalendarRows.filter(
      row => keys.has(row.period)
    );
  }, [allCalendarRows, filteredCells]);

  // Analytics summary
  const analytics = useMemo(
    () => summarizeFireAnalytics(calendarRows),
    [calendarRows]
  );

  const canDownload =
    isValidDateRange && calendarRows.length > 0;

  const suffix = `${startDate}_to_${endDate}`;

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
              Download sampled fire detections including
              coordinates, timestamps, satellite sensor and FRP.
            </p>

            <div className={styles.info}>
              <div>
                <span>Format</span>
                <strong>CSV</strong>
              </div>

              <div>
                <span>Records</span>
                <strong>
                  {observations.length.toLocaleString()}
                </strong>
              </div>
            </div>

            <button
              type="button"
              className={styles.downloadButton}
              disabled={
                !isValidDateRange || !observations.length
              }
              onClick={() =>
                downloadFireObservations(
                  observations,
                  `firesync_observations_${suffix}.csv`
                )
              }
            >
              <Download size={18} />
              Download Observations CSV
            </button>
          </section>

          {/* FIRE HISTORY */}
          <section className={styles.downloadCard}>
            <div className={styles.fileIcon}>
              <CalendarDays size={26} />
            </div>

            <h2>Fire Activity History</h2>

            <p>
              Export monthly detection counts used by
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
                  `firesync_history_${suffix}.csv`
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
              Export monthly fire counts, historical averages,
              standard deviations, anomaly z-scores,
              percentiles and classifications.
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
                  `firesync_fire_analytics_${suffix}.csv`
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
              Export the year-by-month burning activity
              calendar with detection counts, historical
              percentile and activity level.
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
                  `firesync_burning_calendar_${suffix}.csv`
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
            FireSync currently uses generated demonstration
            data, not live satellite measurements.
            Monthly fire counts are demonstration aggregates.
            Observation exports contain sampled demo points.
          </p>

          <p>
            The calendar and monthly analytics include an
            entire month whenever it overlaps your selected
            dates. Anomalies compare each month against the
            other available years for the same calendar month
            (2020–2024). A z-score with absolute value at
            least 2 is flagged as unusual.
          </p>
        </div>

      </div>
    </main>
  );
}
