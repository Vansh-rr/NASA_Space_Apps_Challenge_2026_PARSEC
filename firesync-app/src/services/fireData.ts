/**
 * Explore data adapter: real NASA FIRMS data from the PARSEC API (phase3/api.py).
 * MODIS is the default because it is the only sensor covering every downloaded year (VIIRS starts in 2012,
 * the harmonized record exists where both sensors overlap).
 */
import type { ActivityCell, Bounds, FireObservation, Period } from '../types/fire';
import { toMonthKey } from '../utils/dates';
import { ACTIVITY_UNIT, DEMO_ACTIVITY, exploreFiresFor } from '../data/demoActivity';
import { type ApiObservation, getJson, toObservation } from './api';

export const IS_DEMO_DATA = false;
/** Default region: the one with the full 7-year download. */
export const EXPLORE_REGION = 'british_columbia';
export type ExploreSensor = 'MODIS' | 'VIIRS' | 'harmonized';
export const EXPLORE_SENSORS: Array<{ id: ExploreSensor; label: string; note: string }> = [
  { id: 'MODIS', label: 'MODIS', note: 'raw detections, every downloaded year' },
  { id: 'VIIRS', label: 'VIIRS', note: 'raw detections, 2012 onwards' },
  { id: 'harmonized', label: 'Harmonized', note: 'one point per matched fire, harmonized FRP (years with both sensors)' },
];
/** Shown when no month is selected: July 2023, the record fire season. */
export const DEFAULT_PERIOD: Period = { year: 2023, month: 7 };
/** Enough for every month in the data, so the map is never cut off part way through a month. */
const MAX_POINTS = 50000;

export function activityUnit(sensor: ExploreSensor): string {
  return `${sensor === 'harmonized' ? 'harmonized' : sensor} fire detections per month`;
}

interface ApiActivityRow {
  year: number;
  month: number;
  detections: number;
}

/** Year x month detection counts; every year with data gets all 12 months (no row = 0 detections). */
export async function fetchActivityMatrix(region: string, sensor: ExploreSensor, signal?: AbortSignal): Promise<ActivityCell[]> {
  const rows = await getJson<ApiActivityRow[]>('/activity', { region, sensor }, signal);
  const byKey = new Map(rows.map((r) => [`${r.year}-${r.month}`, r.detections]));
  const years = [...new Set(rows.map((r) => r.year))];
  return years.flatMap((year) =>
    Array.from({ length: 12 }, (_, i) => ({ year, month: i + 1, value: byKey.get(`${year}-${i + 1}`) ?? 0 })),
  );
}

/** All detections of one month for the map. */
export async function fetchExploreObservations(
  region: string,
  period: Period,
  sensor: ExploreSensor,
  signal?: AbortSignal,
): Promise<FireObservation[]> {
  const rows = await getJson<ApiObservation[]>(
    '/observations',
    { region, month: toMonthKey(period.year, period.month), sensor, limit: MAX_POINTS },
    signal,
  );
  return rows.map(toObservation);
}

/** Detections inside a drawn area [west, south, east, north]. */
export function insideArea(observations: FireObservation[], area: Bounds): FireObservation[] {
  const [w, s, e, n] = area;
  return observations.filter((o) => o.longitude >= w && o.longitude <= e && o.latitude >= s && o.latitude <= n);
}

// kept for the Download page, which still uses demo data until it is moved to the API
export function getActivityMatrix(): { cells: ActivityCell[]; unit: string } {
  return { cells: DEMO_ACTIVITY, unit: ACTIVITY_UNIT };
}

export function getExploreObservations(period: Period | null): FireObservation[] {
  return exploreFiresFor(period);
}