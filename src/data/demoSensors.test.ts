import { describe, expect, it } from 'vitest';
import { nextSensors } from '../components/filters/AnalyticsFilters';
import { kpiSensor } from '../services/analyticsService';
import { daysInMonth } from '../utils/dates';
import { peakDates } from '../utils/metrics';
import { DEMO_ACTIVITY } from './demoActivity';
import { demoSensorRecords } from './demoSensors';

describe('demo sensor records', () => {
  const reference = demoSensorRecords('california', '2024-08');

  it('reproduces the reference totals', () => {
    expect(reference.modis.detectionCount).toBe(24738);
    expect(reference.viirs.detectionCount).toBe(26081);
    expect(reference.harmonized.detectionCount).toBe(28459);
  });

  it('peaks on August 22 for every record', () => {
    for (const record of Object.values(reference)) expect(peakDates(record.dailyCounts)).toEqual(['2024-08-22']);
  });

  it('keeps totals, daily sums and active days consistent for other months', () => {
    for (const [region, month] of [['california', '2024-02'], ['oregon', '2023-07'], ['nevada', '2020-01']]) {
      for (const record of Object.values(demoSensorRecords(region, month))) {
        const counts = record.dailyCounts.map((d) => d.count ?? 0);
        expect(counts).toHaveLength(daysInMonth(month));
        expect(counts.reduce((s, v) => s + v, 0)).toBe(record.detectionCount);
        expect(record.activeDays).toBe(counts.filter((c) => c > 0).length);
        expect(counts.every((c) => Number.isInteger(c) && c >= 0)).toBe(true);
      }
    }
  });

  it('is deterministic', () => {
    expect(demoSensorRecords('oregon', '2022-09')).toEqual(demoSensorRecords('oregon', '2022-09'));
  });

  it('records harmonized provenance', () => {
    expect(reference.harmonized.detections.every((d) => (d.sourceIds?.length ?? 0) > 0)).toBe(true);
  });
});

describe('activity matrix', () => {
  it('has 60 cells', () => expect(DEMO_ACTIVITY).toHaveLength(60));
});

describe('sensor selection rules', () => {
  it('lets both raw sensors be selected together', () => expect(nextSensors(['modis'], 'viirs')).toEqual(['modis', 'viirs']));
  it('makes Harmonized replace the raw sensors', () => expect(nextSensors(['modis', 'viirs'], 'harmonized')).toEqual(['harmonized']));
  it('leaves Harmonized mode when a raw sensor is chosen', () => expect(nextSensors(['harmonized'], 'modis')).toEqual(['modis']));
  it('allows clearing everything', () => expect(nextSensors(['viirs'], 'viirs')).toEqual([]));
  it('picks the KPI record without summing', () => {
    expect(kpiSensor(['modis', 'viirs'])).toBe('viirs');
    expect(kpiSensor(['modis'])).toBe('modis');
    expect(kpiSensor(['harmonized'])).toBe('harmonized');
    expect(kpiSensor([])).toBeNull();
  });
});
