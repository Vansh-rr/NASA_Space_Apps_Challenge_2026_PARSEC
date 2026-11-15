import { DEMO_MONTHS, DEMO_YEARS, isReferenceState } from '../data/demoModel';
import { dailyShape, demoScale, demoSensorRecords } from '../data/demoSensors';
import type { AnalyticsFilters, AnalyticsResponse, DailyAnalytics, Metric} from '../types/analytics';
import type { FireObservation, SensorId } from '../types/fire';
import { parseMonth, previousMonth, toMonthKey } from '../utils/dates';
import { absoluteChange, movingAverage, percentChange, zScore } from '../utils/metrics';
import { createRng } from '../utils/random';
import { demoDelay } from './demoDelay';

const METHODOLOGY =
  'Demonstration data, not measured wildfire activity. KPI rule: with Harmonized selected the harmonized ' +
  'record is used; otherwise VIIRS when selected, else MODIS (records are never summed, to avoid double ' +
  'counting). Anomaly is the z-score of the month’s detections against the same calendar month in ' +
  '2020–2024. Trend is a 3-day centered moving average of daily FRP. Changes compare with the previous ' +
  'calendar month under the same rules. The August 2024 California values reproduce the design reference.';

/** Which record drives the KPI cards. See METHODOLOGY. */
export function kpiSensor(sensors: SensorId[]): SensorId | null {
  if (sensors.includes('harmonized')) return 'harmonized';
  if (sensors.includes('viirs')) return 'viirs';
  if (sensors.includes('modis')) return 'modis';
  return null;
}

interface RawKpis {
  detections: number;
  totalFrp: number;
  clusters: number;
  anomaly: number | null;
}

function rawKpis(regionId: string, month: string, sensor: SensorId): RawKpis {
  const detections = demoSensorRecords(regionId, month)[sensor].detectionCount ?? 0;
  const { month: m } = parseMonth(month);
  const baseline = DEMO_YEARS.map((y) => demoSensorRecords(regionId, toMonthKey(y, m))[sensor].detectionCount ?? 0);
  return {
    detections,
    totalFrp: Math.round((118.4 * detections) / 26081 * 10) / 10,
    clusters: Math.round(detections * 0.051455),
    anomaly: zScore(detections, baseline),
  };
}

function buildPeakPeriods(regionId: string, sensor: SensorId): PeakPeriod[] {
  return DEMO_MONTHS
  .map((month) => ({
    month,
    sensor,
    value: demoSensorRecords(regionId, month)[sensor].detectionCount ?? 0,
  }))
  .sort((a, b) => b.value - a.value)
  .slice(0, 3);
}

function buildCurrentVsHistory(regionId: string, month: string, sensor: SensorId): HistoricalMonth {
  const { month: calendarMonth } = parseMonth(month);
  const current = demoSensorRecords(regionId, month)[sensor].detectionCount ?? 0;
  const allSameCalendarMonth = DEMO_YEARS
  .map((y) => demoSensorRecords(regionId, toMonthKey(y, calendarMonth))[sensor].detectionCount ?? 0);
  const rank = allSameCalendarMonth.filter((v) => v <= current).length / allSameCalendarMonth.length * 100;
  return { month, value: current, percentileRank: Math.round(rank) };
}

function buildMetrics(filters: AnalyticsFilters, sensor: SensorId): AnalyticsResponse['metrics'] {
  const current = rawKpis(filters.regionId, filters.month, sensor);
  const prevMonth = previousMonth(filters.month);
  const previous = DEMO_MONTHS.includes(prevMonth) ? rawKpis(filters.regionId, prevMonth, sensor) : null;

  const metrics: AnalyticsResponse['metrics'] = {
    anomaly: {
      value: current.anomaly,
      unit: 'z-score',
      change: absoluteChange(current.anomaly, previous?.anomaly ?? null),
      changeKind: 'absolute',
    },
    totalFrp: metric(current.totalFrp, previous?.totalFrp ?? null, 'MW'),
    detections: metric(current.detections, previous?.detections ?? null, 'count'),
    clusters: metric(current.clusters, previous?.clusters ?? null, 'count'),
  };

  // Design-reference fixtures for the initial screen state.
  const defaultSensors = filters.sensors.length === 2 && !filters.sensors.includes('harmonized');
  if (isReferenceState(filters.regionId, filters.month) && defaultSensors) {
    metrics.anomaly = { value: 2.87, unit: 'z-score', change: 1.24, changeKind: 'absolute' };
    metrics.totalFrp.change = 32.6;
    metrics.detections.change = 12.9;
    metrics.clusters.change = 18.7;
  }
  return metrics;
}

function metric(value: number, previous: number | null, unit: Metric['unit']): Metric {
  return { value, unit, change: percentChange(value, previous), changeKind: 'percent' };
}

function buildDaily(filters: AnalyticsFilters, sensor: SensorId): DailyAnalytics[] {
  const records = demoSensorRecords(filters.regionId, filters.month);
  const scale = demoScale(filters.regionId, filters.month);
  const shape = dailyShape(filters.regionId, filters.month);
  const rng = createRng(`frp:${filters.regionId}:${filters.month}:${sensor}`);
  const sensorAdjust = { modis: 0.95, viirs: 1, harmonized: 1.04 }[sensor];
  const dailyFrp = shape.map((w) => Math.round(1700 * scale * sensorAdjust * w * (0.93 + 0.14 * rng())));
  const trend = movingAverage(dailyFrp, 3);

  return records.modis.dailyCounts.map(({ date }, i) => ({
    date,
    dailyFrpMw: dailyFrp[i],
    trendFrpMw: trend[i] === null ? null : Math.round(trend[i] as number),
    modisDetections: records.modis.dailyCounts[i].count,
    viirsDetections: records.viirs.dailyCounts[i].count,
    harmonizedDetections: records.harmonized.dailyCounts[i].count,
  }));
}

function buildObservations(filters: AnalyticsFilters): FireObservation[] {
  const records = demoSensorRecords(filters.regionId, filters.month);
  if (filters.sensors.includes('harmonized')) return records.harmonized.detections;
  return filters.sensors.flatMap((s) => records[s].detections);
}

/** Demo analytics service. Requires at least one selected sensor. */
export async function fetchAnalytics(filters: AnalyticsFilters, signal?: AbortSignal): Promise<AnalyticsResponse> {
  await demoDelay(signal);
  const sensor = kpiSensor(filters.sensors);
  if (!sensor) throw new Error('Select at least one sensor.');
  return {
    filters,
    metrics: buildMetrics(filters, sensor),
    daily: buildDaily(filters, sensor),
    observations: buildObservations(filters),
    isDemo: true,
    updatedAt: null,
    methodology: METHODOLOGY,
  };
}
