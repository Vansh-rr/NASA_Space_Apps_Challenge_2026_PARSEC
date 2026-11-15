import { describe, expect, it } from 'vitest';
import { distributeTotal, movingAverage, parseCoordinates, peakDates, percentChange, absoluteChange, zScore } from './metrics';
import { niceTicks } from './comparison';
import { axisTickDates, datesOfMonth, daysInMonth, previousMonth } from './dates';

describe('percentChange', () => {
  it('computes a percentage', () => expect(percentChange(120, 100)).toBeCloseTo(20));
  it('is null for a zero or missing baseline', () => {
    expect(percentChange(10, 0)).toBeNull();
    expect(percentChange(10, null)).toBeNull();
    expect(percentChange(null, 10)).toBeNull();
  });
});

describe('absoluteChange', () => {
  it('is the plain difference for z-scores', () => expect(absoluteChange(2.87, 1.63)).toBeCloseTo(1.24));
});

describe('zScore', () => {
  it('is null with zero variance', () => expect(zScore(5, [5, 5, 5])).toBeNull());
  it('is positive above the mean', () => expect(zScore(30, [10, 20, 30])).toBeGreaterThan(0));
});

describe('movingAverage', () => {
  it('averages a centered window and shortens at the edges', () => {
    expect(movingAverage([3, 6, 9, 12], 3)).toEqual([4.5, 6, 9, 10.5]);
  });
  it('skips nulls', () => expect(movingAverage([null, 4, null], 3)).toEqual([4, 4, 4]));
});

describe('distributeTotal', () => {
  it('returns non-negative integers summing exactly to the total', () => {
    const parts = distributeTotal([0.2, 1.7, 3.1, 0.9, 2.2], 24738);
    expect(parts.reduce((s, v) => s + v, 0)).toBe(24738);
    expect(parts.every((p) => Number.isInteger(p) && p >= 0)).toBe(true);
  });
});

describe('peakDates', () => {
  it('reports ties', () => {
    expect(peakDates([{ date: 'a', count: 2 }, { date: 'b', count: 5 }, { date: 'c', count: 5 }])).toEqual(['b', 'c']);
  });
  it('is empty when nothing was detected', () => expect(peakDates([{ date: 'a', count: 0 }, { date: 'b', count: null }])).toEqual([]));
});

describe('parseCoordinates', () => {
  it('accepts latitude, longitude', () => {
    expect(parseCoordinates('38.58, -121.49')).toEqual({ ok: true, latitude: 38.58, longitude: -121.49 });
  });
  it('rejects malformed and out-of-range input', () => {
    expect(parseCoordinates('38.58').ok).toBe(false);
    expect(parseCoordinates('abc, 10').ok).toBe(false);
    expect(parseCoordinates('91, 10').ok).toBe(false);
    expect(parseCoordinates('10, 181').ok).toBe(false);
    expect(parseCoordinates('10,').ok).toBe(false);
  });
});

describe('dates', () => {
  it('handles month lengths and leap years', () => {
    expect(daysInMonth('2024-02')).toBe(29);
    expect(daysInMonth('2023-02')).toBe(28);
    expect(datesOfMonth('2024-08')).toHaveLength(31);
  });
  it('wraps the previous month across years', () => expect(previousMonth('2024-01')).toBe('2023-12'));
  it('always ends axis ticks on the last day', () => {
    for (const month of ['2024-02', '2023-02', '2024-08', '2024-09']) {
      const dates = datesOfMonth(month);
      expect(axisTickDates(dates).at(-1)).toBe(dates.at(-1));
    }
  });
});

describe('niceTicks', () => {
  it('covers the maximum with tidy steps', () => {
    expect(niceTicks(2317)).toEqual([0, 500, 1000, 1500, 2000, 2500]);
    expect(niceTicks(87)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(0)).toEqual([0, 1]);
  });
});
