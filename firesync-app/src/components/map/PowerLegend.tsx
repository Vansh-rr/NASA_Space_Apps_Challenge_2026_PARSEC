import styles from './FireMap.module.css';

/** Fire Radiative Power legend. A log scale: ticks sit at 1, 10, 100 and 1000 MW. */
export function PowerLegend() {
  return (
    <div className={styles.legend} role="group" aria-label="Fire Radiative Power legend, megawatts, logarithmic scale">
      <span className={styles.legendTitle}>Fire Radiative Power (MW)</span>
      <div className={styles.legendBar} aria-hidden="true" />
      <div className={styles.legendTicks}>
        <span>1</span>
        <span>10</span>
        <span>100</span>
        <span>1000+</span>
      </div>
    </div>
  );
}
