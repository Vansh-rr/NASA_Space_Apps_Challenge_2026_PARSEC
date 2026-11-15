import { getJson } from './api';

export interface ModelPreviewMetadata {
  model_run_id: string;
  source_kind: string;
  calibration_kind: string;
  physical_frp_validated: boolean;
  warning: boolean;
  solver: string;
  area_crs: string;
  bbox: [number, number, number, number];
  start_utc: string;
  last_bin_utc: string;
  bin_seconds: number;
  cells: number;
  time_bins: number;
  rows: number;
  observed_rows: number;
  training_observations: { modis: number; viirs: number };
  disclaimer: string;
  source_granules: string[];
}

export interface ModelPreviewFieldItem {
  time: string;
  cell_id: string;
  latitude: number;
  longitude: number;
  p_fire: number;
  usable_observation_count: number;
  coverage_status: 'observed' | 'model_only';
}

export interface ModelPreviewValidation {
  scope: string;
  selected_fold: number;
  comparison: {
    n: number;
    positives: number;
    negatives: number;
    heldout_granules: string[];
  };
}

export interface HourlyProbability {
  time: string;
  meanPFire: number;
}

export interface CellSummaryRow {
  cell_id: string;
  latitude: number;
  longitude: number;
  meanPFire: number;
  maxPFire: number;
  observedBins: number;
}

export interface ModelPreviewData {
  metadata: ModelPreviewMetadata;
  items: ModelPreviewFieldItem[];
  validation: ModelPreviewValidation;
}

export function previewDateRange(
  metadata: Pick<ModelPreviewMetadata, 'start_utc' | 'last_bin_utc'>,
): { start: string; end: string } {
  return {
    start: metadata.start_utc.slice(0, 10),
    end: metadata.last_bin_utc.slice(0, 10),
  };
}

export async function fetchModelPreview(signal?: AbortSignal): Promise<ModelPreviewData> {
  const metadata = await getJson<ModelPreviewMetadata>('/model-preview/metadata', undefined, signal);
  const { start, end } = previewDateRange(metadata);
  const items: ModelPreviewFieldItem[] = [];
  let total: number | undefined;
  do {
    const page = await getJson<{ items: ModelPreviewFieldItem[]; total: number }>(
      '/model-preview/field', { start, end, bbox: metadata.bbox.join(','), limit: 10000, offset: items.length }, signal);
    if (!Number.isSafeInteger(page.total) || page.total < 0 || (total !== undefined && total !== page.total)) {
      throw new Error('Preview changed during loading. Please retry.');
    }
    total = page.total;
    if (!page.items.length && items.length < total) throw new Error('Incomplete model preview. Please retry.');
    items.push(...page.items);
    if (items.length > total) throw new Error('Invalid model preview row count.');
  } while (items.length < total);
  const validation = await getJson<ModelPreviewValidation>('/model-preview/validation', undefined, signal);
  return { metadata, items, validation };
}

export function hourlyMeanProbability(items: ModelPreviewFieldItem[]): HourlyProbability[] {
  const byTime = new Map<string, { sum: number; count: number }>();
  for (const item of items) {
    const entry = byTime.get(item.time) ?? { sum: 0, count: 0 };
    entry.sum += item.p_fire;
    entry.count += 1;
    byTime.set(item.time, entry);
  }
  return Array.from(byTime.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, { sum, count }]) => ({ time, meanPFire: sum / count }));
}

export function cellSummary(items: ModelPreviewFieldItem[]): CellSummaryRow[] {
  const byCell = new Map<
    string,
    { latitude: number; longitude: number; sum: number; count: number; max: number; observedBins: number }
  >();
  for (const item of items) {
    const entry = byCell.get(item.cell_id);
    if (!entry) {
      byCell.set(item.cell_id, {
        latitude: item.latitude,
        longitude: item.longitude,
        sum: item.p_fire,
        count: 1,
        max: item.p_fire,
        observedBins: item.coverage_status === 'observed' ? 1 : 0,
      });
    } else {
      entry.sum += item.p_fire;
      entry.count += 1;
      if (item.p_fire > entry.max) entry.max = item.p_fire;
      if (item.coverage_status === 'observed') entry.observedBins += 1;
    }
  }
  return Array.from(byCell.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([cell_id, v]) => ({
      cell_id,
      latitude: v.latitude,
      longitude: v.longitude,
      meanPFire: v.sum / v.count,
      maxPFire: v.max,
      observedBins: v.observedBins,
    }));
}
