/**
 * Demo per-sensor records shared by Analytics and Compare, so both pages agree.
 * The reference state (California, August 2024) reproduces the design fixtures exactly;
 * every other region/month is scaled from it with seeded variation.
 *
 * The harmonized series is a labeled fixture. It is NOT computed by summing or blending
 * MODIS and VIIRS; a real harmonized record needs a defined cross-sensor method.
 */
import type { SensorComparison } from '../types/comparison';
import type { FireObservation, SensorId } from '../types/fire';
import { datesOfMonth, parseMonth } from '../utils/dates';
import { distributeTotal } from '../utils/metrics';
import { createRng } from '../utils/random';
import { isReferenceState, monthFactor } from './demoModel';
import { generateDemoFires } from './demoFires';
import { getRegion } from './regions';
import { SENSOR_ORDER } from './sensors';

const REFERENCE_TOTALS: Record<SensorId, number> = { modis: 24738, viirs: 26081, harmonized: 28459 };
const REFERENCE_MEAN_FRP: Record<SensorId, number> = { modis: 118.4, viirs: 121.7, harmonized: 123.6 };

/** Scale of a region/month relative to the reference state. */
export function demoScale(regionId: string, month: string): number {
  if (isReferenceState(regionId, month)) return 1;
  const jitter = 0.94 + 0.12 * createRng(`scale:${regionId}:${month}`)();
  return getRegion(regionId).scale * monthFactor(month) * jitter;
}

/** Peak day of the month (1-based). August 2024 peaks on the 22nd as in the reference. */
function peakDay(regionId: string, month: string, days: number): number {
  if (parseMonth(month).year === 2024 && parseMonth(month).month === 8) return 22;
  return 10 + Math.floor(createRng(`peak:${regionId}:${month}`)() * (days - 15));
}

/** Shared daily shape: slow irregular rise, sharp peak, faster decline. */
export function dailyShape(regionId: string, month: string): number[] {
  const dates = datesOfMonth(month);
  const peak = peakDay(regionId, month, dates.length);
  const rng = createRng(`shape:${regionId}:${month}`);
  return dates.map((_, i) => {
    const day = i + 1;
    const width = day < peak ? 8 : 4.3;
    const noise = day === peak ? 1.04 : 0.94 + 0.12 * rng();
    return (0.075 + Math.exp(-(((day - peak) / width) ** 2))) * noise;
  });
}

const cache = new Map<string, Record<SensorId, SensorComparison>>();

export function demoSensorRecords(regionId: string, month: string): Record<SensorId, SensorComparison> {
  const key = `${regionId}:${month}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const scale = demoScale(regionId, month);
  const dates = datesOfMonth(month);
  const shape = dailyShape(regionId, month);
  const reference = isReferenceState(regionId, month);

  // One pool of points; each raw sensor sees a subset, the harmonized record keeps provenance.
  const poolSize = Math.min(260, Math.max(10, Math.round((REFERENCE_TOTALS.harmonized * scale) / 150)));
  const pool = generateDemoFires({ regionId, month, count: poolSize, sensor: 'harmonized', seedKey: 'compare' });
  const membership = createRng(`membership:${key}`);
  const bySensor: Record<SensorId, FireObservation[]> = { modis: [], viirs: [], harmonized: [] };
  for (const fire of pool) {
    const inModis = membership() < 0.66;
    const inViirs = membership() < 0.86 || !inModis;
    const sourceIds: string[] = [];
    if (inModis) {
      bySensor.modis.push({ ...fire, id: `${fire.id}-modis`, sensor: 'modis' });
      sourceIds.push(`${fire.id}-modis`);
    }
    if (inViirs) {
      bySensor.viirs.push({ ...fire, id: `${fire.id}-viirs`, sensor: 'viirs' });
      sourceIds.push(`${fire.id}-viirs`);
    }
    bySensor.harmonized.push({ ...fire, sourceIds });
  }

  const records = {} as Record<SensorId, SensorComparison>;
  for (const sensor of SENSOR_ORDER) {
    const rng = createRng(`sensor:${sensor}:${key}`);
    const total = Math.round(REFERENCE_TOTALS[sensor] * scale);
    const weights = shape.map((w) => w * (0.985 + 0.03 * rng()));
    const counts = distributeTotal(weights, total);
    const meanFrp = reference
      ? REFERENCE_MEAN_FRP[sensor]
      : Math.round(REFERENCE_MEAN_FRP[sensor] * (0.72 + 0.28 * Math.min(1, monthFactor(month) * 1.2)) * (0.96 + 0.08 * rng()) * 10) / 10;
    records[sensor] = {
      sensor,
      detectionCount: total,
      meanFrpMw: total > 0 ? meanFrp : null,
      activeDays: counts.filter((c) => c > 0).length,
      dailyCounts: dates.map((date, i) => ({ date, count: counts[i] })),
      detections: bySensor[sensor],
    };
  }

  cache.set(key, records);
  return records;
}
