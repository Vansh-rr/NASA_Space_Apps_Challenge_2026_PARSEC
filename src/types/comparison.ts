import type { FireObservation, SensorId } from './fire';

export interface ComparisonFilters {
  regionId: string;
  /** YYYY-MM */
  month: string;
  focusedSensor: SensorId;
}

export interface DailyCount {
  /** YYYY-MM-DD, aggregated in UTC by the demo service. */
  date: string;
  count: number | null;
}

export interface SensorComparison {
  sensor: SensorId;
  detectionCount: number | null;
  meanFrpMw: number | null;
  activeDays: number | null;
  dailyCounts: DailyCount[];
  detections: FireObservation[];
}

export interface ComparisonResponse {
  regionId: string;
  month: string;
  records: Record<SensorId, SensorComparison>;
  isDemo: boolean;
  updatedAt: string | null;
  methodology: string;
}
