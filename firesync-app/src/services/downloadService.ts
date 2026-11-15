import { getJson } from './api';
import type { ExploreSensor } from './fireData';
import type { ActivityCell } from '../types/fire';
import type { FireCalendarRow } from '../utils/fireDownloadAnalytics';

interface ActivityResponseRow { year: number; month: number; detections: number }
interface HistoryResponse {
  years: Array<{
    year: number;
    coverage_state?: string | null;
    n_detections?: number | null;
    anomaly?: Record<string, {
      z_score?: number | null;
      percentile?: number | null;
      anomaly_class?: string;
      baseline_median?: number | null;
      n_baseline_years?: number | null;
    }>;
  }>;
}

/** Use the real /activity records; absent months remain absent (not fabricated zeros). */
export async function fetchDownloadData(
  region: string, sensor: ExploreSensor, signal?: AbortSignal,
): Promise<{ cells: ActivityCell[]; calendar: FireCalendarRow[]; historyAvailable: boolean }> {
  const monthly = await getJson<ActivityResponseRow[]>('/activity', { region, sensor }, signal);
  const cells: ActivityCell[] = monthly.map(row => ({
    year: row.year, month: row.month, value: row.detections,
  }));
  const distinctMonths = [...new Set(cells.map(row => row.month))];
  let historyAvailable = true;
  const history = new Map<string, HistoryResponse['years'][number]>();
  // A single failing history endpoint should not prevent the calendar/count exports.
  await Promise.all(distinctMonths.map(async month => {
    try {
      const response = await getJson<HistoryResponse>('/history', { region, month, sensor }, signal);
      for (const row of response.years) history.set(`${row.year}-${month}`, row);
    } catch (err) {
      if (signal?.aborted) throw err;
      historyAvailable = false;
    }
  }));
  const calendar: FireCalendarRow[] = cells.map(cell => {
    const record = history.get(`${cell.year}-${cell.month}`);
    const anomaly = record?.anomaly?.n_detections;
    const z = anomaly?.z_score ?? null;
    return {
      ...cell,
      period: `${cell.year}-${String(cell.month).padStart(2, '0')}`,
      baselineMean: null,
      baselineStdDev: null,
      baselineMedian: anomaly?.baseline_median ?? null,
      baselineYears: anomaly?.n_baseline_years ?? null,
      coverageState: record?.coverage_state ?? 'Unknown',
      anomalyZScore: z,
      historicalPercentile: anomaly?.percentile ?? null,
      activityCategory: anomaly?.anomaly_class ?? 'Unavailable',
    };
  });
  return { cells, calendar, historyAvailable };
}
