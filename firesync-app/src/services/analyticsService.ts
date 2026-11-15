import type { AnalyticsFilters, AnalyticsResponse } from '../types/analytics';
import type { SensorId } from '../types/fire';
import { datesOfMonth } from '../utils/dates';
import { movingAverage } from '../utils/metrics';
import { getJson, toObservation } from './api';
import { fillDailyCounts, fillDailySums, type ApiComparisonResponse, type ApiSensorComparison } from './comparisonService';

const METHODOLOGY =
  'KPIs use one record: Harmonized if selected, else VIIRS, else MODIS (records are never summed). ' +
  'Total FRP is the sum of reported FRP over all detections in the month; it is not fire energy, because ' +
  'one fire is seen on several overpasses. Anomaly = z-score of this month\'s detection count against the same calendar ' +
  'month in the other downloaded years (VIIRS when VIIRS is the KPI record, else MODIS; requires verified complete regional coverage and at least 3 other complete years). ' +
  'Fire clusters = fire events that started this month (nearby detections grouped in space and time). ' +
  'Month-to-month change is not connected yet. ' +
  'The harmonized record defaults to the identity baseline (harmonized FRP equals ' +
  'MODIS FRP); the Bayesian model is shown separately as an exploratory preview on the Model Preview page. Data covers British Columbia for the months loaded into the database, in UTC.';

/** Which record drives the KPI cards. See METHODOLOGY. */
export function kpiSensor(sensors: SensorId[]): SensorId | null {
  if (sensors.includes('harmonized')) return 'harmonized';
  if (sensors.includes('viirs')) return 'viirs';
  if (sensors.includes('modis')) return 'modis';
  return null;
}

/** /history response: one row per downloaded year for one calendar month. */
export interface ApiHistory {
  years: Array<{
    year: number;
    n_detections: number | null;
    n_fire_events_started: number | null;
    anomaly: Record<string, { z_score: number | null; anomaly_class: string } | undefined>;
  }>;
}

/** The raw sensor used for anomaly and clusters (harmonized has no anomaly yet, so it falls back to MODIS). */
export function historySensor(sensor: SensorId): 'MODIS' | 'VIIRS' {
  return sensor === 'viirs' ? 'VIIRS' : 'MODIS';
}

/** z-score and fire clusters of the selected month from /history; null when unknown. */
export function historyMetrics(month: string, history: ApiHistory | null): { zScore: number | null; clusters: number | null } {
  const year = Number(month.slice(0, 4));
  const row = history?.years.find((y) => y.year === year);
  return {
    zScore: row?.anomaly?.n_detections?.z_score ?? null,
    // 0 events in a month with detections means events were not computed for that year (2003, 2010)
    clusters: row && row.n_fire_events_started && row.n_fire_events_started > 0 ? row.n_fire_events_started : null,
  };
}

export function buildAnalytics(filters: AnalyticsFilters, api: ApiComparisonResponse, history: ApiHistory | null = null): AnalyticsResponse {
  const sensor = kpiSensor(filters.sensors);
  if (!sensor) throw new Error('Select at least one sensor.');

  const bySensor = new Map<SensorId, ApiSensorComparison>();
  for (const s of api.sensors) {
    bySensor.set(s.sensor.toLowerCase() as SensorId, s);
  }
  const rec = bySensor.get(sensor);
  const hasData = Boolean(rec && !rec.note && rec.daily.length);
  const knownFrp = (rec?.daily ?? []).filter((d) => d.sum_frp_mw !== null && d.sum_frp_mw !== undefined);
  const sumFrp = knownFrp.length ? knownFrp.reduce((acc, d) => acc + d.sum_frp_mw!, 0) : null;

  const dailyFrp = fillDailySums(filters.month, rec?.daily ?? []);
  const trend = movingAverage(dailyFrp, 3);
  const modisCounts = fillDailyCounts(filters.month, bySensor.get('modis')?.daily ?? []);
  const viirsCounts = fillDailyCounts(filters.month, bySensor.get('viirs')?.daily ?? []);
  const harmonizedCounts = fillDailyCounts(filters.month, bySensor.get('harmonized')?.daily ?? []);

  const daily = datesOfMonth(filters.month).map((date, i) => ({
    date,
    dailyFrpMw: dailyFrp[i],
    trendFrpMw: dailyFrp[i] === null || trend[i] === null ? null : Math.round(trend[i] as number),
    modisDetections: modisCounts[i].count,
    viirsDetections: viirsCounts[i].count,
    harmonizedDetections: harmonizedCounts[i].count,
  }));

  const hist = historyMetrics(filters.month, history);

  const selectedSensors: SensorId[] = filters.sensors.includes('harmonized') ? ['harmonized'] : filters.sensors;
  const observations = selectedSensors.flatMap((s) => (bySensor.get(s)?.sample ?? []).map(toObservation));

  return {
    filters,
    metrics: {
      detections: { value: hasData ? rec!.detections : null, unit: 'count', change: null, changeKind: 'percent' },
      totalFrp: { value: sumFrp === null ? null : Math.round(sumFrp * 10) / 10, unit: 'MW', change: null, changeKind: 'percent' },
      anomaly: { value: hist.zScore === null ? null : Math.round(hist.zScore * 100) / 100, unit: 'z-score', change: null, changeKind: 'absolute' },
      clusters: { value: hist.clusters, unit: 'count', change: null, changeKind: 'percent' },
    },
    daily,
    observations,
    isDemo: Boolean(api.is_demo),
    updatedAt: null,
    methodology: METHODOLOGY,
  };
}

export async function fetchAnalytics(filters: AnalyticsFilters, signal?: AbortSignal): Promise<AnalyticsResponse> {
  const sensor = kpiSensor(filters.sensors);
  if (!sensor) throw new Error('Select at least one sensor.');
  const [api, history] = await Promise.all([
    getJson<ApiComparisonResponse>('/comparison', { region: filters.regionId, month: filters.month, sample: 300 }, signal),
    // history is optional: if the API has no /history yet, anomaly and clusters just stay "Unavailable"
    getJson<ApiHistory>(
      '/history',
      { region: filters.regionId, month: Number(filters.month.slice(5, 7)), sensor: historySensor(sensor) },
      signal,
    ).catch(() => null),
  ]);
  return buildAnalytics(filters, api, history);
}
