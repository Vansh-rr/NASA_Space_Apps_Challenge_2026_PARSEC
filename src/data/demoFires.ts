import type { FireObservation, SensorId } from '../types/fire';
import { daysInMonth } from '../utils/dates';
import { createRng, gaussian } from '../utils/random';
import { getRegion } from './regions';

interface GenerateOptions {
  regionId: string;
  /** YYYY-MM */
  month: string;
  count: number;
  sensor: SensorId;
  /** Distinguishes independent fixture sets for the same region and month. */
  seedKey: string;
}

/**
 * Deterministic demo fire observations. Positions cluster around plausible fire-prone
 * areas; FRP is skewed towards low values with a few intense points.
 */
export function generateDemoFires({ regionId, month, count, sensor, seedKey }: GenerateOptions): FireObservation[] {
  const region = getRegion(regionId);
  const rng = createRng(`fires:${seedKey}:${regionId}:${month}`);
  const totalWeight = region.clusters.reduce((s, c) => s + c.weight, 0);
  const [west, south, east, north] = region.bounds;
  const days = daysInMonth(month);
  const fires: FireObservation[] = [];

  for (let i = 0; i < count; i += 1) {
    let pick = rng() * totalWeight;
    let cluster = region.clusters[0];
    for (const c of region.clusters) {
      pick -= c.weight;
      if (pick <= 0) {
        cluster = c;
        break;
      }
    }
    const longitude = clamp(cluster.longitude + gaussian(rng) * cluster.spread * 1.5, west + 0.1, east - 0.1);
    const latitude = clamp(cluster.latitude + gaussian(rng) * cluster.spread * 1.3, south + 0.1, north - 0.1);
    const frpMw = Math.round(10 ** (rng() ** 5 * 3.2) * 10) / 10;
    const day = 1 + Math.floor(rng() * days);
    const hour = Math.floor(rng() * 24);
    const minute = Math.floor(rng() * 60);
    fires.push({
      id: `${seedKey}-${regionId}-${month}-${i}`,
      longitude: Math.round(longitude * 10000) / 10000,
      latitude: Math.round(latitude * 10000) / 10000,
      frpMw,
      observedAt: `${month}-${pad(day)}T${pad(hour)}:${pad(minute)}:00Z`,
      sensor,
      isDemo: true,
    });
  }
  return fires;
}

const pad = (n: number) => String(n).padStart(2, '0');
const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
