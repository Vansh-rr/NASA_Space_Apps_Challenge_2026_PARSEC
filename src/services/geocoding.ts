/**
 * Geocoder adapter. The demo resolves a small documented list of places; swap `geocode`
 * for a real provider (server-side key) without touching the search UI.
 */
import type { SelectedLocation } from '../types/fire';
import { demoDelay } from './demoDelay';

export const DEMO_PLACES: SelectedLocation[] = [
  { label: 'Redding, CA', latitude: 40.59, longitude: -122.39 },
  { label: 'Chico, CA', latitude: 39.73, longitude: -121.84 },
  { label: 'Sacramento, CA', latitude: 38.58, longitude: -121.49 },
  { label: 'San Francisco, CA', latitude: 37.77, longitude: -122.42 },
  { label: 'San Jose, CA', latitude: 37.34, longitude: -121.89 },
  { label: 'Fresno, CA', latitude: 36.74, longitude: -119.79 },
  { label: 'Reno, NV', latitude: 39.53, longitude: -119.81 },
  { label: 'Yosemite National Park, CA', latitude: 37.87, longitude: -119.54 },
  { label: 'Lake Tahoe, CA', latitude: 39.1, longitude: -120.03 },
  { label: 'Los Angeles, CA', latitude: 34.05, longitude: -118.24 },
  { label: 'San Diego, CA', latitude: 32.72, longitude: -117.16 },
];

export function matchPlaces(query: string): SelectedLocation[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const name = (p: SelectedLocation) => p.label.toLowerCase();
  const exact = DEMO_PLACES.filter((p) => name(p) === q || name(p).split(',')[0] === q);
  if (exact.length > 0) return exact;
  return DEMO_PLACES.filter((p) => name(p).includes(q));
}

export async function geocode(query: string, signal?: AbortSignal): Promise<SelectedLocation[]> {
  await demoDelay(signal);
  return matchPlaces(query);
}
