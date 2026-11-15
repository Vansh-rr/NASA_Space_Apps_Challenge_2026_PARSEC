import { describe, expect, it } from 'vitest';
import { buildAnalytics, historicalComparison, historyMetrics, historySensor, type ApiHistory } from './analyticsService';
import { fillDailySums, type ApiComparisonResponse } from './comparisonService';

const FAKE_API: ApiComparisonResponse = {
  region: 'british_columbia',
  month: '2023-07',
  sensors: [
    {
      sensor: 'MODIS',
      detections: 120,
      mean_frp_mw: 40.5,
      active_days: 2,
      daily: [
        { date: '2023-07-01 00:00:00', detections: 50, sum_frp_mw: 100.2 },
        { date: '2023-07-03 00:00:00', detections: 70, sum_frp_mw: 200.3 },
      ],
      sample: [
        { id: 1, latitude: 51, longitude: -120, frp_mw: 25, observed_at: '2023-07-01T12:00:00Z', sensor: 'MODIS' },
      ],
    },
    {
      sensor: 'VIIRS',
      detections: 340,
      mean_frp_mw: 18.2,
      active_days: 2,
      daily: [
        { date: '2023-07-01 00:00:00', detections: 140, sum_frp_mw: 410.14 },
        { date: '2023-07-02 00:00:00', detections: 200, sum_frp_mw: 589.86 },
      ],
      sample: [
        { id: 2, latitude: 52, longitude: -121, frp_mw: 12, observed_at: '2023-07-02T12:00:00Z', sensor: 'VIIRS' },
      ],
    },
    {
      sensor: 'HARMONIZED',
      detections: 95,
      mean_frp_mw: 42.0,
      active_days: 1,
      daily: [
        { date: '2023-07-01 00:00:00', detections: 95, sum_frp_mw: 250.5 },
      ],
      sample: [
        { id: 'h1', latitude: 53, longitude: -122, frp_mw: 30, observed_at: '2023-07-01T12:00:00Z', sensor: 'HARMONIZED' },
      ],
    },
  ],
};

describe('fillDailySums', () => {
  it('puts 0 on missing days and null sum_frp_mw', () => {
    const sums = fillDailySums('2023-07', [
      { date: '2023-07-01 00:00:00', detections: 10, sum_frp_mw: 12.5 },
      { date: '2023-07-03 00:00:00', detections: 5, sum_frp_mw: null },
    ]);
    expect(sums).toHaveLength(31);
    expect(sums[0]).toBe(12.5);
    expect(sums[1]).toBe(0);
    expect(sums[2]).toBe(0);
  });
});

describe('buildAnalytics', () => {
  it('builds 31 daily rows, VIIRS KPIs for modis+viirs, totalFrp sum, and null anomaly/clusters', () => {
    const res = buildAnalytics(
      { regionId: 'british_columbia', month: '2023-07', sensors: ['modis', 'viirs'] },
      FAKE_API,
    );
    expect(res.daily).toHaveLength(31);
    expect(res.metrics.detections.value).toBe(340);
    expect(res.metrics.totalFrp.value).toBe(1000);
    expect(res.metrics.anomaly.value).toBeNull();
    expect(res.metrics.clusters.value).toBeNull();
    expect(res.observations.map((o) => o.sensor)).toEqual(['modis', 'viirs']);
  });

  it('uses harmonized KPIs and only harmonized observations when harmonized is selected', () => {
    const res = buildAnalytics(
      { regionId: 'british_columbia', month: '2023-07', sensors: ['modis', 'viirs', 'harmonized'] },
      FAKE_API,
    );
    expect(res.metrics.detections.value).toBe(95);
    expect(res.metrics.totalFrp.value).toBe(250.5);
    expect(res.observations).toHaveLength(1);
    expect(res.observations[0].sensor).toBe('harmonized');
  });
});

describe('history metrics (anomaly + clusters)', () => {
  const HISTORY: ApiHistory = {
    years: [
      { year: 2018, n_detections: 900, n_fire_events_started: 40, anomaly: { n_detections: { z_score: 0.4, anomaly_class: 'normal' } } },
      { year: 2023, n_detections: 2400, n_fire_events_started: 75, anomaly: { n_detections: { z_score: 2.345, anomaly_class: 'much_above_normal' } } },
    ],
  };

  it('picks the selected year', () => {
    expect(historyMetrics('2023-07', HISTORY)).toEqual({ zScore: 2.345, clusters: 75 });
    expect(historyMetrics('2010-07', HISTORY)).toEqual({ zScore: null, clusters: null });
    expect(historyMetrics('2023-07', null)).toEqual({ zScore: null, clusters: null });
  });

  it('fills the anomaly and cluster cards', () => {
    const out = buildAnalytics({ regionId: 'british_columbia', month: '2023-07', sensors: ['modis', 'viirs'] }, FAKE_API, HISTORY);
    expect(out.metrics.anomaly.value).toBe(2.35);
    expect(out.metrics.clusters.value).toBe(75);
  });

  it('uses VIIRS only when VIIRS drives the cards', () => {
    expect(historySensor('viirs')).toBe('VIIRS');
    expect(historySensor('modis')).toBe('MODIS');
    expect(historySensor('harmonized')).toBe('MODIS');
  });
});
describe('historical comparison (this month vs the median)', () => {
  const HISTORY: ApiHistory = {
    years: [
      {
        year: 2024, n_detections: 27975, n_fire_events_started: 1338,
        anomaly: { n_detections: { z_score: 1.52, anomaly_class: 'much_above_normal', baseline_median: 7571, n_baseline_years: 6 } },
      },
      { year: 2010, n_detections: 2488, n_fire_events_started: 0, anomaly: {} },
    ],
  };

  it('gives value, median and class for the selected year', () => {
    expect(historicalComparison('2024-07', HISTORY, 'MODIS')).toEqual({
      sensor: 'MODIS', value: 27975, median: 7571, baselineYears: 6, anomalyClass: 'much_above_normal',
    });
  });

  it('is null without history or without a baseline', () => {
    expect(historicalComparison('2010-07', HISTORY, 'MODIS')).toBeNull();
    expect(historicalComparison('2003-07', HISTORY, 'MODIS')).toBeNull();
    expect(historicalComparison('2024-07', null, 'MODIS')).toBeNull();
  });
});
