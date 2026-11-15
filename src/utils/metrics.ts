/** Percentage change. Null when the baseline is zero or unavailable. */
export function percentChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

export function absoluteChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null) return null;
  return current - previous;
}

/** Centered moving average. Edges use the values that exist; nulls are skipped. */
export function movingAverage(values: Array<number | null>, window = 3): Array<number | null> {
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    const slice = values
      .slice(Math.max(0, i - half), i + half + 1)
      .filter((v): v is number => v !== null);
    if (slice.length === 0) return null;
    return slice.reduce((sum, v) => sum + v, 0) / slice.length;
  });
}

/** z-score of a value against a baseline sample. Null for zero variance or tiny samples. */
export function zScore(value: number, baseline: number[]): number | null {
  if (baseline.length < 2) return null;
  const mean = baseline.reduce((s, v) => s + v, 0) / baseline.length;
  const variance = baseline.reduce((s, v) => s + (v - mean) ** 2, 0) / (baseline.length - 1);
  if (variance === 0) return null;
  return (value - mean) / Math.sqrt(variance);
}

/** Split an integer total across weights so the parts are non-negative integers summing exactly. */
export function distributeTotal(weights: number[], total: number): number[] {
  const weightSum = weights.reduce((s, w) => s + w, 0);
  if (weightSum <= 0 || total <= 0) return weights.map(() => 0);
  const raw = weights.map((w) => (w / weightSum) * total);
  const parts = raw.map(Math.floor);
  let remainder = total - parts.reduce((s, v) => s + v, 0);
  const order = raw
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction);
  for (let i = 0; remainder > 0; i = (i + 1) % order.length, remainder -= 1) {
    parts[order[i].index] += 1;
  }
  return parts;
}

/** Dates sharing the maximum count. Empty when there is no positive value. */
export function peakDates(daily: Array<{ date: string; count: number | null }>): string[] {
  let max = 0;
  for (const d of daily) if (d.count !== null && d.count > max) max = d.count;
  if (max === 0) return [];
  return daily.filter((d) => d.count === max).map((d) => d.date);
}

export type CoordinateResult =
  | { ok: true; latitude: number; longitude: number }
  | { ok: false; error: string };

/** Parse "latitude, longitude" input such as "38.58, -121.49". */
export function parseCoordinates(input: string): CoordinateResult {
  const parts = input.split(',').map((p) => p.trim());
  if (parts.length !== 2 || parts.some((p) => p === '')) {
    return { ok: false, error: 'Enter latitude and longitude separated by a comma, for example 38.58, -121.49.' };
  }
  const [latitude, longitude] = parts.map(Number);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return { ok: false, error: 'Latitude and longitude must both be numbers.' };
  }
  if (latitude < -90 || latitude > 90) {
    return { ok: false, error: 'Latitude must be between -90 and 90.' };
  }
  if (longitude < -180 || longitude > 180) {
    return { ok: false, error: 'Longitude must be between -180 and 180.' };
  }
  return { ok: true, latitude, longitude };
}
