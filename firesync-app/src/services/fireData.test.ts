import { describe, expect, it } from 'vitest';
import { insideArea } from './fireData';
import type { FireObservation } from '../types/fire';

const fire = (id: string, longitude: number, latitude: number): FireObservation => ({
  id, longitude, latitude, frpMw: 10, observedAt: '2023-07-01T00:00:00Z', sensor: 'modis', isDemo: false,
});

describe('insideArea', () => {
  it('keeps only detections inside [west, south, east, north]', () => {
    const fires = [fire('in', -122, 53), fire('west', -126, 53), fire('north', -122, 58)];
    expect(insideArea(fires, [-124, 52, -120, 55]).map((f) => f.id)).toEqual(['in']);
  });
});
