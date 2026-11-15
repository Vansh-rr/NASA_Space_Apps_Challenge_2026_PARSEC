export type SensorId = 'modis' | 'viirs' | 'harmonized';

export type SearchMode = 'place' | 'coordinates';

export interface FireObservation {
  id: string;
  longitude: number;
  latitude: number;
  /** Fire radiative power in megawatts. Null when not reported. */
  frpMw: number | null;
  /** ISO timestamp with timezone. */
  observedAt: string;
  sensor: SensorId;
  /** True for generated fixtures. Never present real records as demo or the reverse. */
  isDemo: boolean;
  /** Provenance for a harmonized record. */
  sourceIds?: string[];
  scanKm?: number;
  trackKm?: number;
}

export interface ActivityCell {
  year: number;
  /** 1–12 */
  month: number;
  /** Monthly detection count; the same aggregate for every cell. */
  value: number | null;
  isDemo?: boolean;
}

export interface Period {
  year: number;
  month: number;
}

export interface SelectedLocation {
  latitude: number;
  longitude: number;
  label: string;
}

export interface ExploreFilters {
  mode: SearchMode;
  query: string;
  selectedPeriod: Period | null;
  selectedLocation: SelectedLocation | null;
}

/** [west, south, east, north] */
export type Bounds = [number, number, number, number];
