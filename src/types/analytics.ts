import type { FireObservation, SensorId } from './fire';

export interface PeakPeriod {
  month: string;   // YYYY-MM
  value: number;   // detection count
  sensor: SensorId;
}

export interface HistoricalMonth {
  month: string;   // YYYY-MM
  value: number;
  percentileRank: number;  // 0–100, where current month ranks among all same calendar months
}

export interface AnalyticsFilters {
  regionId: string;
  /** YYYY-MM */
  month: string;
  sensors: SensorId[];
}

export interface DailyAnalytics {
  /** YYYY-MM-DD, aggregated in UTC by the demo service. */
  date: string;
  dailyFrpMw: number | null;
  trendFrpMw: number | null;
  modisDetections: number | null;
  viirsDetections: number | null;
  harmonizedDetections: number | null;
}

export interface Metric {
  value: number | null;
  unit: 'MW' | 'count' | 'z-score';
  change: number | null;
  changeKind: 'percent' | 'absolute';
}

export interface AnalyticsResponse {
  filters: AnalyticsFilters;
  metrics: {
    anomaly: Metric;
    totalFrp: Metric;
    detections: Metric;
    clusters: Metric;
  };
  daily: DailyAnalytics[];
  observations: FireObservation[];
  isDemo: boolean;
  updatedAt: string | null;
  methodology: string;
  peakPeriods: PeakPeriod[];
  currentVsHistory: HistoricalMonth;
}
