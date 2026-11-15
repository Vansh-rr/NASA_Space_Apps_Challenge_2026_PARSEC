import type { ActivityCell, FireObservation, Period } from '../types/fire';
import { toMonthKey } from '../utils/dates';
import { createRng } from '../utils/random';
import { DEMO_YEARS, periodFactor } from './demoModel';
import { generateDemoFires } from './demoFires';

/** The aggregate behind the Explore heatmap. Defined once so every cell uses the same metric. */
export const ACTIVITY_UNIT = 'fire detections per month';

const rng = createRng('activity-matrix');

/** 5 years × 12 months of demo monthly detection counts. */
export const DEMO_ACTIVITY: ActivityCell[] = DEMO_YEARS.flatMap((year) =>
  Array.from({ length: 12 }, (_, i) => ({
    year,
    month: i + 1,
    value: Math.round(26000 * periodFactor(year, i + 1) * (0.92 + 0.16 * rng())),
  })),
);

/** Map points for Explore: a sample proportional to each month's activity. */
const DEMO_EXPLORE_FIRES: FireObservation[] = DEMO_ACTIVITY.flatMap((cell) =>
  generateDemoFires({
    regionId: 'california',
    month: toMonthKey(cell.year, cell.month),
    count: Math.max(3, Math.round((cell.value ?? 0) / 520)),
    sensor: 'harmonized',
    seedKey: 'explore',
  }),
);

export function exploreFiresFor(period: Period | null): FireObservation[] {
  if (!period) return DEMO_EXPLORE_FIRES;
  const prefix = toMonthKey(period.year, period.month);
  return DEMO_EXPLORE_FIRES.filter((f) => f.observedAt.startsWith(prefix));
}
