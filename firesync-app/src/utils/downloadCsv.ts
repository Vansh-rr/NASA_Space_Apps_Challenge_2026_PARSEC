
import type {
  ActivityCell,
  FireObservation
} from '../types/fire';

import type {
  FireCalendarRow
} from './fireDownloadAnalytics';

// Escape CSV values correctly
function csvValue(
  value: string | number | boolean | null | undefined
): string {
  if (value === null || value === undefined) return '';

  const text = String(value);

  const safeText =
    typeof value === 'string' &&
    /^[\s]*[=+\-@\t\r]/.test(text)
      ? "'" + text
      : text;

  return `"${safeText.replace(/"/g, '""')}"`;
}

// Convert rows to CSV
function createCsv(
  headers: string[],
  rows: (string | number | boolean | null | undefined)[][]
): string {
  return [
    headers.map(csvValue).join(','),
    ...rows.map(row => row.map(csvValue).join(','))
  ].join('\r\n');
}

// Download CSV to user's computer
function saveCsv(filename: string, content: string): void {
  const blob = new Blob(
    ['\uFEFF', content],
    { type: 'text/csv;charset=utf-8;' }
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  window.setTimeout(
    () => URL.revokeObjectURL(url),
    1000
  );
}

// 1. Fire Observations CSV
export function downloadFireObservations(
  observations: FireObservation[],
  filename = 'firesync_observations.csv'
): void {
  const headers = [
    'Fire ID',
    'Latitude',
    'Longitude',
    'FRP (MW)',
    'Observed At',
    'Sensor',
    'Demo Data',
    'Source IDs'
  ];

  const rows = observations.map(fire => [
    fire.id,
    fire.latitude,
    fire.longitude,
    fire.frpMw,
    fire.observedAt,
    fire.sensor,
    fire.isDemo,
    fire.sourceIds?.join(';') ?? ''
  ]);

  saveCsv(filename, createCsv(headers, rows));
}

// 2. Fire Activity History CSV
export function downloadFireHistory(
  cells: ActivityCell[],
  filename = 'firesync_fire_history.csv'
): void {
  const headers = [
    'Year',
    'Month',
    'Period',
    'Fire Detections',
    'Data Type'
  ];

  const rows = cells.map(cell => [
    cell.year,
    cell.month,
    `${cell.year}-${String(cell.month).padStart(2, '0')}`,
    cell.value,
    'Demo'
  ]);

  saveCsv(filename, createCsv(headers, rows));
}

// 3. Burning Activity Calendar CSV
export function downloadBurningCalendar(
  rows: FireCalendarRow[],
  filename = 'firesync_burning_calendar.csv'
): void {
  const headers = [
    'Year',
    'Month',
    'Period',
    'Fire Detections',
    'Historical Percentile (%)',
    'Activity Category',
    'Demo Data'
  ];

  const data = rows.map(row => [
    row.year,
    row.month,
    row.period,
    row.value,
    row.historicalPercentile,
    row.activityCategory,
    true
  ]);

  saveCsv(filename, createCsv(headers, data));
}

// 4. Fire Analytics CSV
export function downloadFireAnalytics(
  rows: FireCalendarRow[],
  filename = 'firesync_fire_analytics.csv'
): void {
  const headers = [
    'Year',
    'Month',
    'Period',
    'Fire Detections',
    'Baseline Mean Detections',
    'Baseline Std Dev',
    'Anomaly Z-Score',
    'Historical Percentile (%)',
    'Anomaly Classification',
    'Anomaly (abs Z >= 2)',
    'Demo Data'
  ];

  const data = rows.map(row => [
    row.year,
    row.month,
    row.period,
    row.value,
    row.baselineMean,
    row.baselineStdDev,
    row.anomalyZScore,
    row.historicalPercentile,
    row.activityCategory,
    row.anomalyZScore !== null &&
      Math.abs(row.anomalyZScore) >= 2,
    true
  ]);

  saveCsv(filename, createCsv(headers, data));
}
