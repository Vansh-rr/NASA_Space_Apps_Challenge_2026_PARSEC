import type { AnalyticsFilters, AnalyticsResponse } from '../types/analytics';
import type { SensorId } from '../types/fire';
import { datesOfMonth } from '../utils/dates';
import { movingAverage } from '../utils/metrics';
import { getJson, toObservation } from './api';
import { fillDailyCounts, fillDailySums, type ApiComparisonResponse, type ApiSensorComparison } from './comparisonService';

const METHODOLOGY =
  'KPIs use one record: Harmonized if selected, else VIIRS, else MODIS (records are never summed). ' +
  'Total FRP is the sum of reported FRP over all detections in the month; it is not fire energy, because ' +
  'one fire is seen on several overpasses. Anomaly, clusters and month-to-month change are not connected to the API yet. ' +
  'The harmonized record is the identity baseline (harmonized FRP equals ' +
  'MODIS FRP); the Bayesian model is shown separately as an exploratory preview on the Model Preview page. Data covers British Columbia for the months loaded into the database, in UTC.';

/** Which record drives the KPI cards. See METHODOLOGY. */
export function kpiSensor(sensors: SensorId[]): SensorId | null {
  if (sensors.includes('harmonized')) return 'harmonized';
  if (sensors.includes('viirs')) return 'viirs';
  if (sensors.includes('modis')) return 'modis';
  return null;
}

export function buildAnalytics(filters: AnalyticsFilters, api: ApiComparisonResponse): AnalyticsResponse {
  const sensor = kpiSensor(filters.sensors);
  if (!sensor) throw new Error('Select at least one sensor.');

  const bySensor = new Map<SensorId, ApiSensorComparison>();
  for (const s of api.sensors) {
    bySensor.set(s.sensor.toLowerCase() as SensorId, s);
  }
  const rec = bySensor.get(sensor);
  const sumFrp = (rec?.daily ?? []).reduce((acc, d) => acc + (d.sum_frp_mw ?? 0), 0);

  const dailyFrp = fillDailySums(filters.month, rec?.daily ?? []);
  const trend = movingAverage(dailyFrp, 3);
  const modisCounts = fillDailyCounts(filters.month, bySensor.get('modis')?.daily ?? []);
  const viirsCounts = fillDailyCounts(filters.month, bySensor.get('viirs')?.daily ?? []);
  const harmonizedCounts = fillDailyCounts(filters.month, bySensor.get('harmonized')?.daily ?? []);

  const daily = datesOfMonth(filters.month).map((date, i) => ({
    date,
    dailyFrpMw: dailyFrp[i],
    trendFrpMw: trend[i] === null ? null : Math.round(trend[i] as number),
    modisDetections: modisCounts[i].count,
    viirsDetections: viirsCounts[i].count,
    harmonizedDetections: harmonizedCounts[i].count,
  }));

  const selectedSensors: SensorId[] = filters.sensors.includes('harmonized') ? ['harmonized'] : filters.sensors;
  const observations = selectedSensors.flatMap((s) => (bySensor.get(s)?.sample ?? []).map(toObservation));

  return {
    filters,
    metrics: {
      detections: { value: rec?.detections ?? 0, unit: 'count', change: null, changeKind: 'percent' },
      totalFrp: { value: Math.round(sumFrp * 10) / 10, unit: 'MW', change: null, changeKind: 'percent' },
      anomaly: { value: null, unit: 'z-score', change: null, changeKind: 'absolute' },
      clusters: { value: null, unit: 'count', change: null, changeKind: 'percent' },
    },
    daily,
    observations,
    isDemo: false,
    updatedAt: null,
    methodology: METHODOLOGY,
  };
}

export async function fetchAnalytics(filters: AnalyticsFilters, signal?: AbortSignal): Promise<AnalyticsResponse> {
  if (!kpiSensor(filters.sensors)) throw new Error('Select at least one sensor.');
  const api = await getJson<ApiComparisonResponse>(
    '/comparison',
    { region: filters.regionId, month: filters.month, sample: 300 },
    signal,
  );
  return buildAnalytics(filters, api);
}
