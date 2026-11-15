import type { SensorId } from '../types/fire';

export interface SensorConfig {
  id: SensorId;
  label: string;
  subtitle: string;
  color: string;
  tint: string;
}

export const SENSORS: Record<SensorId, SensorConfig> = {
  modis: { id: 'modis', label: 'MODIS', subtitle: 'Aqua/Terra', color: 'var(--modis)', tint: 'var(--modis-tint)' },
  viirs: { id: 'viirs', label: 'VIIRS', subtitle: 'Suomi NPP', color: 'var(--viirs)', tint: 'var(--viirs-tint)' },
  harmonized: {
    id: 'harmonized',
    label: 'Harmonized',
    subtitle: 'Consistent fire record',
    color: 'var(--harmonized)',
    tint: 'var(--harmonized-tint)',
  },
};

/** Recharts needs literal colours rather than CSS variables. */
export const SENSOR_HEX: Record<SensorId, string> = {
  modis: '#397FCA',
  viirs: '#DC4F9C',
  harmonized: '#EC7D28',
};

export const SENSOR_ORDER: SensorId[] = ['modis', 'viirs', 'harmonized'];
