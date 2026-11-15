/**
 * DEMO DATA MODEL
 * Everything derived from this file is generated fixture data, not measured wildfire activity.
 * It encodes a plausible fire-season shape so every view tells the same story until the
 * backend is connected.
 */
import { parseMonth, toMonthKey } from '../utils/dates';

export const DEMO_YEARS = [2020, 2021, 2022, 2023, 2024];

/** Relative activity by calendar month (Jan–Dec). Peaks in August. */
const MONTH_FACTOR = [0.05, 0.05, 0.1, 0.15, 0.26, 0.46, 0.8, 1, 0.84, 0.5, 0.2, 0.07];

/** Relative activity by year. */
const YEAR_FACTOR: Record<number, number> = { 2020: 0.9, 2021: 0.94, 2022: 0.74, 2023: 0.8, 2024: 1 };

/** Activity relative to the reference month (August 2024 = 1). */
export function periodFactor(year: number, month: number): number {
  return (YEAR_FACTOR[year] ?? 0.8) * MONTH_FACTOR[month - 1];
}

export function monthFactor(month: string): number {
  const p = parseMonth(month);
  return periodFactor(p.year, p.month);
}

/** Newest first: 2024-12 … 2020-01. */
export const DEMO_MONTHS: string[] = [...DEMO_YEARS]
  .reverse()
  .flatMap((year) => Array.from({ length: 12 }, (_, i) => toMonthKey(year, 12 - i)));

export const REFERENCE_REGION = 'california';
export const REFERENCE_MONTH = '2024-08';

export function isReferenceState(regionId: string, month: string): boolean {
  return regionId === REFERENCE_REGION && month === REFERENCE_MONTH;
}
