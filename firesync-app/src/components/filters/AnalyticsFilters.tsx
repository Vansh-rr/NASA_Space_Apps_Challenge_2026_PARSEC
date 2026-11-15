import { Check } from 'lucide-react';
import { SENSOR_ORDER, SENSORS } from '../../data/sensors';
import type { AnalyticsFilters as Filters } from '../../types/analytics';
import type { SensorId } from '../../types/fire';
import { MonthSelect, RegionSelect } from './FilterSelects';
import shared from '../../styles/shared.module.css';
import styles from '../../pages/AnalyticsPage.module.css';

interface Props {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

/**
 * Sensor rule (a prototype decision): MODIS and VIIRS can be compared together;
 * Harmonized is a separate record, so selecting it replaces the raw sensors and
 * selecting a raw sensor leaves Harmonized mode.
 */
export function nextSensors(current: SensorId[], toggled: SensorId): SensorId[] {
  if (current.includes(toggled)) return current.filter((s) => s !== toggled);
  if (toggled === 'harmonized') return ['harmonized'];
  return SENSOR_ORDER.filter((s) => s !== 'harmonized' && (s === toggled || current.includes(s)));
}

export function AnalyticsFilters({ filters, onChange }: Props) {
  return (
    <section className={`${shared.card} ${styles.filters}`} aria-label="Filters">
      <RegionSelect id="analytics-region" value={filters.regionId} onChange={(regionId) => onChange({ ...filters, regionId })} />
      <MonthSelect id="analytics-month" value={filters.month} onChange={(month) => onChange({ ...filters, month })} />

      <fieldset className={styles.sensors}>
        <legend className={shared.fieldLabel}>Sensor comparison</legend>
        <div className={styles.sensorPills}>
          {SENSOR_ORDER.map((sensor) => {
            const checked = filters.sensors.includes(sensor);
            return (
              <label key={sensor} className={`${styles.pill} ${checked ? styles.pillChecked : ''}`}>
                <input
                  type="checkbox"
                  className="visually-hidden"
                  checked={checked}
                  onChange={() => onChange({ ...filters, sensors: nextSensors(filters.sensors, sensor) })}
                />
                <span className={styles.box} aria-hidden="true">
                  {checked && <Check size={14} strokeWidth={3} />}
                </span>
                {SENSORS[sensor].label}
              </label>
            );
          })}
        </div>
        <p className={styles.sensorHelp}>Harmonized is a separate record and replaces the raw sensors when selected.</p>
      </fieldset>
    </section>
  );
}
