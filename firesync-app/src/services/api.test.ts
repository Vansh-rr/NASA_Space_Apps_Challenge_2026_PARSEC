import { describe, expect, it } from 'vitest';
import { toObservation } from './api';
import { fillDailyCounts } from './comparisonService';

describe('toObservation', () => {
  it('maps API fields to FireObservation with string id and lowercased sensor', () => {
    const obs = toObservation({
      id: 42,
      latitude: 50.67,
      longitude: -120.33,
      frp_mw: 125.4,
      observed_at: '2023-07-15T21:30:00+00:00',
      sensor: 'VIIRS',
      is_demo: false,
    });
    expect(obs).toEqual({
      id: '42',
      latitude: 50.67,
      longitude: -120.33,
      frpMw: 125.4,
      observedAt: '2023-07-15T21:30:00+00:00',
      sensor: 'viirs',
      isDemo: false,
    });
  });

  it('preserves string id, null frp_mw, and harmonized sensor', () => {
    const obs = toObservation({
      id: 'mg_001',
      latitude: 52.0,
      longitude: -121.0,
      frp_mw: null,
      observed_at: '2023-07-16T08:00:00Z',
      sensor: 'MODIS',
      is_demo: true,
    });
    expect(obs.id).toBe('mg_001');
    expect(obs.frpMw).toBeNull();
    expect(obs.sensor).toBe('modis');
    expect(obs.isDemo).toBe(true);
  });
});

describe('fillDailyCounts', () => {
  it('returns every day of the month and preserves missing days as unknown', () => {
    const daily = fillDailyCounts('2023-07', [
      { date: '2023-07-02', detections: 14 },
      { date: '2023-07-15', detections: 89 },
    ]);
    expect(daily).toHaveLength(31);
    expect(daily[0]).toEqual({ date: '2023-07-01', count: null });
    expect(daily[1]).toEqual({ date: '2023-07-02', count: 14 });
    expect(daily[14]).toEqual({ date: '2023-07-15', count: 89 });
    expect(daily[30]).toEqual({ date: '2023-07-31', count: null });
    expect(daily.reduce((sum, d) => sum + (d.count ?? 0), 0)).toBe(103);
  });

  it('truncates timestamped API dates to their YYYY-MM-DD prefix', () => {
    const daily = fillDailyCounts('2023-07', [
      { date: '2023-07-01 00:00:00', detections: 42 },
    ]);
    expect(daily[0]).toEqual({ date: '2023-07-01', count: 42 });
  });
});
