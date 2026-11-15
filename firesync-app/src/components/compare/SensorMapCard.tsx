import { forwardRef } from 'react';
import { Activity, CalendarDays, Flame, Layers, Satellite } from 'lucide-react';
import type { City } from '../../data/regions';
import { SENSORS } from '../../data/sensors';
import type { MapSyncGroup } from '../../hooks/useSyncedMapCamera';
import type { SensorComparison } from '../../types/comparison';
import type { Bounds } from '../../types/fire';
import { formatCount, formatOneDecimal } from '../../utils/formatters';
import { FireMap } from '../map/FireMap';
import { DemoBadge } from '../shared/States';
import styles from '../../pages/ComparePage.module.css';

interface Props {
  record: SensorComparison;
  bounds: Bounds;
  cities: City[];
  sync: MapSyncGroup;
  isDemo: boolean;
  focused: boolean;
  /** The Harmonized card: larger type and a taller map. */
  large?: boolean;
}

export const SensorMapCard = forwardRef<HTMLElement, Props>(function SensorMapCard(
  { record, bounds, cities, sync, isDemo, focused, large },
  ref,
) {
  const config = SENSORS[record.sensor];
  const Icon = record.sensor === 'harmonized' ? Layers : Satellite;
  const accent = { '--accent': config.color, '--tint': config.tint } as React.CSSProperties;

  return (
    <article
      ref={ref}
      className={`${styles.card} ${large ? styles.cardLarge : ''} ${focused ? styles.cardFocused : ''}`}
      style={accent}
      aria-label={`${config.label} map and summary`}
    >
      <header className={styles.cardHeader}>
        <span className={styles.sensorIcon} aria-hidden="true">
          <Icon size={large ? 28 : 22} />
        </span>
        <div className={styles.cardTitles}>
          <h3 className={styles.cardTitle}>{config.label}</h3>
          <p className={styles.cardSubtitle}>{config.subtitle}</p>
        </div>
        <div className={styles.cardStatus}>
          {focused && <span className={styles.focusTag}>Focused</span>}
          {isDemo && <DemoBadge />}
        </div>
      </header>

      <FireMap
        className={styles.cardMap}
        label={`${config.label} fire detections map`}
        caption="Fire detections"
        tone="dark"
        compact={!large}
        showLegend={false}
        observations={record.detections}
        bounds={bounds}
        cities={cities}
        sync={sync}
      />

      <dl className={styles.tiles}>
        <div className={styles.tile}>
          <dt>
            <Flame size={15} aria-hidden="true" /> Detections
          </dt>
          <dd>{formatCount(record.detectionCount)}</dd>
        </div>
        <div className={styles.tile}>
          <dt>
            <Activity size={15} aria-hidden="true" /> Mean FRP (MW)
          </dt>
          <dd>{formatOneDecimal(record.meanFrpMw)}</dd>
        </div>
        <div className={styles.tile}>
          <dt>
            <CalendarDays size={15} aria-hidden="true" /> Active fire days
          </dt>
          <dd>{formatCount(record.activeDays)}</dd>
        </div>
      </dl>
    </article>
  );
});
