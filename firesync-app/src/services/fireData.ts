/**
 * Explore data adapter: real NASA FIRMS data from the PARSEC API (phase3/api.py).
 * MODIS is used because it is the only sensor covering every downloaded year (VIIRS starts in 2012).
 */
import type { ActivityCell, FireObservation, Period } from '../types/fire';
import { toMonthKey } from '../utils/dates';
import { type ApiObservation, getJson, getJsonPage, toObservation } from './api';

export const IS_DEMO_DATA = false;
export const EXPLORE_REGION = 'british_columbia';
export const EXPLORE_SENSOR = 'MODIS';
export const ACTIVITY_UNIT = 'MODIS fire detections per month';
/** Shown when no month is selected: July 2023, the record fire season. */
export const DEFAULT_PERIOD: Period = { year: 2023, month: 7 };
/** Page size, not a cap on the displayed month. */
const MAX_POINTS = 50000;

interface ApiActivityRow {
  year: number;
  month: number;
  detections: number;
  is_demo?: boolean;
}

/** No API row means unknown coverage, not zero fires. */
export async function fetchActivityMatrix(signal?: AbortSignal): Promise<ActivityCell[]> {
  const rows = await getJson<ApiActivityRow[]>('/activity', { region: EXPLORE_REGION, sensor: EXPLORE_SENSOR }, signal);
  const byKey = new Map(rows.map((r) => [`${r.year}-${r.month}`, r.detections]));
  const years = [...new Set(rows.map((r) => r.year))];
  const isDemo = rows.some((r) => r.is_demo);
  return years.flatMap((year) =>
    Array.from({ length: 12 }, (_, i) => ({ year, month: i + 1, value: byKey.get(`${year}-${i + 1}`) ?? null, isDemo })),
  );
}

/** All MODIS detections of one month for the map. */
export async function fetchExploreObservations(period: Period, signal?: AbortSignal): Promise<FireObservation[]> {
  const all: ApiObservation[] = [];
  let total: number | undefined;
  do {
    const page = await getJsonPage<ApiObservation[]>('/observations',
      { region: EXPLORE_REGION, month: toMonthKey(period.year, period.month),
        sensor: EXPLORE_SENSOR, limit: MAX_POINTS, offset: all.length }, signal);
    const header = page.headers.get('X-Total-Count');
    const count = header === null ? NaN : Number(header);
    if (!Number.isSafeInteger(count) || count < 0 || (total !== undefined && count !== total)) {
      throw new Error('Observation count is missing or changed during paging. Please retry.');
    }
    total = count;
    if (!page.data.length && all.length < total) throw new Error('Incomplete observation page. Please retry.');
    all.push(...page.data);
    if (all.length > total) throw new Error('Observation pages exceed the reported count. Please retry.');
  } while (all.length < total);
  return all.map(toObservation);
}
