import { describe, expect, it } from 'vitest';
import { cellSummary, hourlyMeanProbability, type ModelPreviewFieldItem } from './modelPreviewService';

const SAMPLE_ITEMS: ModelPreviewFieldItem[] = [
  {
    time: '2023-07-01T14:00:00+00:00',
    cell_id: 'cell_b',
    latitude: 59.382,
    longitude: -137.545,
    p_fire: 0.4,
    usable_observation_count: 0,
    coverage_status: 'model_only',
  },
  {
    time: '2023-07-01T13:00:00+00:00',
    cell_id: 'cell_b',
    latitude: 59.382,
    longitude: -137.545,
    p_fire: 0.2,
    usable_observation_count: 1,
    coverage_status: 'observed',
  },
  {
    time: '2023-07-01T13:00:00+00:00',
    cell_id: 'cell_a',
    latitude: 59.344,
    longitude: -137.571,
    p_fire: 0.1,
    usable_observation_count: 2,
    coverage_status: 'observed',
  },
  {
    time: '2023-07-01T14:00:00+00:00',
    cell_id: 'cell_a',
    latitude: 59.344,
    longitude: -137.571,
    p_fire: 0.3,
    usable_observation_count: 1,
    coverage_status: 'observed',
  },
];

describe('hourlyMeanProbability', () => {
  it('computes mean p_fire per distinct time in ascending order', () => {
    const out = hourlyMeanProbability(SAMPLE_ITEMS);
    expect(out).toHaveLength(2);
    expect(out[0].time).toBe('2023-07-01T13:00:00+00:00');
    expect(out[0].meanPFire).toBeCloseTo(0.15, 6);
    expect(out[1].time).toBe('2023-07-01T14:00:00+00:00');
    expect(out[1].meanPFire).toBeCloseTo(0.35, 6);
  });
});

describe('cellSummary', () => {
  it('returns one row per cell sorted by cell_id with means, maxes, and observedBins', () => {
    const out = cellSummary(SAMPLE_ITEMS);
    expect(out).toHaveLength(2);
    expect(out.map((r) => r.cell_id)).toEqual(['cell_a', 'cell_b']);

    expect(out[0].latitude).toBe(59.344);
    expect(out[0].longitude).toBe(-137.571);
    expect(out[0].meanPFire).toBeCloseTo(0.2, 6);
    expect(out[0].maxPFire).toBeCloseTo(0.3, 6);
    expect(out[0].observedBins).toBe(2);

    expect(out[1].latitude).toBe(59.382);
    expect(out[1].longitude).toBe(-137.545);
    expect(out[1].meanPFire).toBeCloseTo(0.3, 6);
    expect(out[1].maxPFire).toBeCloseTo(0.4, 6);
    expect(out[1].observedBins).toBe(1);
  });
});
