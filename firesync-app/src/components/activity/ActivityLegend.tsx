import styles from '../../pages/ExplorePage.module.css';

export function ActivityLegend() {
  return (
    <div className={styles.activityLegend} role="group" aria-label="Fire activity level legend: pale yellow is low, dark red is high">
      <span className={styles.activityLegendTitle}>Fire Activity Level</span>
      <div className={styles.activityLegendBar} aria-hidden="true" />
      <div className={styles.activityLegendEnds}>
        <span>Low</span>
        <span>High</span>
      </div>
      <span>Grey: coverage unknown</span>
    </div>
  );
}
