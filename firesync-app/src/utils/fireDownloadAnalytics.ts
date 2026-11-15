import type { ActivityCell } from '../types/fire';

export interface FireCalendarRow extends ActivityCell {
  period: string;
  baselineMean: number | null;
  baselineMedian?: number | null;
  baselineYears?: number | null;
  coverageState?: string;
  baselineStdDev: number | null;
  anomalyZScore: number | null;
  historicalPercentile: number | null;
  activityCategory:
    | 'Unavailable'
    | (string & {})
    | 'Unusual high'
    | 'Above normal'
    | 'Normal'
    | 'Below normal'
    | 'Unusual low'
    | 'Insufficient baseline';
}

const round = (value: number, places = 2) =>
  Number(value.toFixed(places));

// Compare each month with the same month in other years.
export function buildFireCalendarRows(
  cells: ActivityCell[]
): FireCalendarRow[] {
  return [...cells]
    .sort((a, b) => a.year - b.year || a.month - b.month)
    .map(cell => {
      const baseline = cells
        .filter(
          other =>
            other.month === cell.month &&
            other.year !== cell.year
        )
        .map(other => other.value);

      const mean = baseline.length
        ? baseline.reduce((sum, value) => sum + value, 0) /
          baseline.length
        : null;

      const variance =
        baseline.length > 1 && mean !== null
          ? baseline.reduce(
              (sum, value) => sum + (value - mean) ** 2,
              0
            ) / (baseline.length - 1)
          : null;

      const std =
        variance !== null ? Math.sqrt(variance) : null;

      const z =
        mean !== null && std !== null && std > 0
          ? (cell.value - mean) / std
          : null;

      const percentile = baseline.length
        ? (baseline.filter(value => value <= cell.value).length /
            baseline.length) *
          100
        : null;

      const activityCategory: FireCalendarRow['activityCategory'] =
        z === null
          ? 'Insufficient baseline'
          : z >= 2
          ? 'Unusual high'
          : z >= 1
          ? 'Above normal'
          : z <= -2
          ? 'Unusual low'
          : z <= -1
          ? 'Below normal'
          : 'Normal';

      return {
        ...cell,
        period: `${cell.year}-${String(cell.month).padStart(2, '0')}`,
        baselineMean: mean === null ? null : round(mean),
        baselineStdDev: std === null ? null : round(std),
        anomalyZScore: z === null ? null : round(z),
        historicalPercentile:
          percentile === null ? null : round(percentile),
        activityCategory,
      };
    });
}

export function summarizeFireAnalytics(
  rows: FireCalendarRow[]
) {
  const counts = rows.map(row => row.value);

  const total = counts.reduce(
    (sum, value) => sum + value,
    0
  );

  const anomalous = rows.filter(
    row =>
      row.anomalyZScore !== null &&
      Math.abs(row.anomalyZScore) >= 2
  );

  const highest = rows.length
    ? rows.reduce((a, b) =>
        a.value >= b.value ? a : b
      )
    : null;

  return {
    months: rows.length,
    total,
    monthlyAverage: rows.length
      ? round(total / rows.length)
      : 0,
    peakPeriod: highest?.period ?? '—',
    peakDetections: highest?.value ?? 0,
    anomalies: anomalous.length,
  };
}
