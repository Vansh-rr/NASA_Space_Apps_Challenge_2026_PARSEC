import { Layers, Satellite } from 'lucide-react';
import { SENSOR_ORDER, SENSORS } from '../../data/sensors';
import type { ComparisonFilters } from '../../types/comparison';
import type { SensorId } from '../../types/fire';
import { MonthSelect, RegionSelect } from '../filters/FilterSelects';
import { DemoBadge } from '../shared/States';
import shared from '../../styles/shared.module.css';
import styles from '../../pages/ComparePage.module.css';

interface Props {
  filters: ComparisonFilters;
  isDemo: boolean;
  updatedAt: string | null;
  isUpdating: boolean;
  onChange: (filters: ComparisonFilters) => void;
  onFocusSensor: (sensor: SensorId) => void;
}

function relativeTime(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return 'Updated just now';
  if (minutes < 60) return `Updated ${minutes} min ago`;
  return `Updated ${Math.round(minutes / 60)} h ago`;
}

export function ComparisonToolbar({ filters, isDemo, updatedAt, isUpdating, onChange, onFocusSensor }: Props) {
  return (
    <section className={styles.toolbar} aria-label="Filters">
      <div className={styles.toolbarInner}>
        <RegionSelect id="compare-region" value={filters.regionId} onChange={(regionId) => onChange({ ...filters, regionId })} />
        <MonthSelect id="compare-month" value={filters.month} onChange={(month) => onChange({ ...filters, month })} />

        <fieldset className={styles.focusField}>
          <legend className={shared.fieldLabel}>Sensor comparison</legend>
          <div className={styles.focusGroup}>
            {SENSOR_ORDER.map((sensor) => {
              const checked = filters.focusedSensor === sensor;
              const Icon = sensor === 'harmonized' ? Layers : Satellite;
              return (
                <label
                  key={sensor}
                  className={`${styles.focusOption} ${checked ? styles.focusOptionActive : ''}`}
                  style={checked ? { color: sensor === 'harmonized' ? '#a8500f' : sensor === 'viirs' ? '#a82f73' : '#1f5ea6' } : undefined}
                >
                  <input
                    type="radio"
                    name="focused-sensor"
                    className="visually-hidden"
                    checked={checked}
                    onChange={() => onFocusSensor(sensor)}
                  />
                  <Icon size={18} aria-hidden="true" />
                  {SENSORS[sensor].label}
                </label>
              );
            })}
          </div>
          <p className={styles.focusHelp}>Highlights one record. All three stay visible for comparison.</p>
        </fieldset>

        <p className={styles.toolbarStatus} aria-live="polite">
          {isDemo ? <DemoBadge /> : updatedAt ? relativeTime(updatedAt) : null}
          {isUpdating && <span className={shared.updating}>Updating…</span>}
        </p>
      </div>
    </section>
  );
}
