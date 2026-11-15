import { SENSOR_ORDER, SENSORS } from '../data/sensors';
import type { ComparisonResponse } from '../types/comparison';
import { fullDateLabel, dayLabel } from './dates';
import { peakDates } from './metrics';

/** Tidy axis ticks from 0 to just above `max`, with at most five steps (e.g. 2,317 -> 0, 500 … 2,500). */
export function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].map((m) => (m * magnitude) / 10).concat([1, 2, 2.5, 5, 10].map((m) => m * magnitude))
    .find((candidate) => max / candidate <= 5) as number;
  const count = Math.ceil(max / step);
  return Array.from({ length: count + 1 }, (_, i) => i * step);
}

/** One set of ticks shared by all three charts, so their heights compare fairly. */
export function sharedTicks(data: ComparisonResponse): number[] {
  const max = Math.max(0, ...SENSOR_ORDER.flatMap((s) => data.records[s].dailyCounts.map((d) => d.count ?? 0)));
  return niceTicks(max);
}

/** A truthful one-line summary of when detections peak, including ties and disagreements. */
export function peakSummary(data: ComparisonResponse): string {
  const peaks = SENSOR_ORDER.map((s) => ({ sensor: s, dates: peakDates(data.records[s].dailyCounts) }));
  if (peaks.every((p) => p.dates.length === 0)) return 'No detections were recorded in this period.';
  const single = peaks.every((p) => p.dates.length === 1);
  if (single && peaks.every((p) => p.dates[0] === peaks[0].dates[0])) {
    const [, month, day] = fullDateLabel(peaks[0].dates[0]).match(/^(\w+) (\d+)/) ?? [];
    return `Daily detections peak on ${month} ${day} across all three sensor records.`;
  }
  const parts = peaks.map((p) => {
    const label = SENSORS[p.sensor].label;
    if (p.dates.length === 0) return `${label} has no detections`;
    return `${label} on ${p.dates.map(dayLabel).join(' and ')}`;
  });
  return `Peak days differ between records: ${parts.join('; ')}.`;
}
