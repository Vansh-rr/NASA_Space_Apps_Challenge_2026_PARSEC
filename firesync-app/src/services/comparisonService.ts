import type { ComparisonResponse, DailyCount, SensorComparison } from '../types/comparison';
import type { SensorId } from '../types/fire';
import { datesOfMonth } from '../utils/dates';
import { type ApiObservation, getJson, toObservation } from './api';

const METHODOLOGY =
  'Counts and mean FRP are computed in UTC from satellite detections inside the study region bounding box. ' +
  'Active fire days are days with at least one detection. Map points show a deterministic sample of up to 300 ' +
  'detections per record. By default the harmonized record shows one point per matched MODIS detection with FRP ' +
  'from the default identity baseline (harmonized FRP equals MODIS FRP); the Bayesian harmonization model is shown ' +
  'separately as an exploratory preview on the Model Preview page. Data covers British Columbia for the months loaded into the database.';

export interface ApiDailyRow {
  date: string;
  detections: number;
  sum_frp_mw?: number | null;
}

export interface ApiSensorComparison {
  sensor: string;
  detections: number;
  mean_frp_mw: number | null;
  active_days: number;
  daily: ApiDailyRow[];
  sample: ApiObservation[];
  note?: string;
}

export interface ApiComparisonResponse {
  region: string;
  month: string;
  sensors: ApiSensorComparison[];
  is_demo?: boolean;
}

/** Fills every date of `month` in `dailyCounts`, using null when the API has no row for that day. */
export function fillDailyCounts(month: string, rows: Array<{ date: string; detections?: number; count?: number | null }>): DailyCount[] {
  const byDate = new Map<string, number>();
  for (const d of rows) {
    const c = d.detections ?? d.count;
    if (c !== null && c !== undefined) byDate.set(d.date.slice(0, 10), c);
  }
  return datesOfMonth(month).map((date) => ({
    date,
    count: byDate.get(date) ?? null,
  }));
}

/** Fills every date of `month` with `sum_frp_mw`, preserving null when a day or FRP is missing. */
export function fillDailySums(
  month: string,
  rows: Array<{ date: string; detections?: number; sum_frp_mw?: number | null }>,
): Array<number | null> {
  const byDate = new Map<string, number | null>();
  for (const d of rows) {
    byDate.set(d.date.slice(0, 10), d.sum_frp_mw ?? null);
  }
  return datesOfMonth(month).map((date) => byDate.get(date) ?? null);
}

/** Loads all three sensor records for one region and month. */
export async function fetchComparison(regionId: string, month: string, signal?: AbortSignal): Promise<ComparisonResponse> {
  const res = await getJson<ApiComparisonResponse>('/comparison', { region: regionId, month, sample: 300 }, signal);
  const records = {} as Record<SensorId, SensorComparison>;
  for (const s of res.sensors) {
    const sensor = s.sensor.toLowerCase() as SensorId;
    records[sensor] = {
      sensor,
      detectionCount: s.note || !s.daily.length ? null : s.detections,
      meanFrpMw: s.mean_frp_mw,
      activeDays: s.note || !s.daily.length ? null : s.active_days,
      dailyCounts: fillDailyCounts(month, s.daily),
      detections: s.sample.map(toObservation),
    };
  }
  return {
    regionId: res.region ?? regionId,
    month: res.month ?? month,
    records,
    isDemo: Boolean(res.is_demo),
    updatedAt: null,
    methodology: METHODOLOGY,
  };
}
