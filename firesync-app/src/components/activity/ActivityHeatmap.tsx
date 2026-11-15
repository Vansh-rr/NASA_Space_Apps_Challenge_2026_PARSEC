import type { ActivityCell, Period } from '../../types/fire';
import { MONTH_SHORT, monthLabel, toMonthKey } from '../../utils/dates';
import { formatCount, rampColor } from '../../utils/formatters';
import styles from '../../pages/ExplorePage.module.css';

export const ACTIVITY_RAMP = ['#FFF0AF', '#FFD173', '#FF8D3E', '#C72F27', '#800E22'];

interface Props {
  cells: ActivityCell[];
  unit: string;
  selected: Period | null;
  onToggle: (period: Period) => void;
}

/** 5 × 12 matrix of monthly activity. One scale is shared by the whole matrix. */
export function ActivityHeatmap({ cells, unit, selected, onToggle }: Props) {
  const max = Math.max(1, ...cells.map((c) => c.value ?? 0));
  const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => b - a);

  return (
    <div className={styles.heatmapScroll} role="group" aria-label="Fire activity by year and month. Select a month to filter the map.">
      <div className={styles.heatmap}>
        <div className={styles.heatmapRow} aria-hidden="true">
          <span />
          {MONTH_SHORT.map((m) => (
            <span key={m} className={styles.monthLabel}>
              {m}
            </span>
          ))}
        </div>
        {years.map((year) => (
          <div key={year} className={styles.heatmapRow}>
            <span className={styles.yearLabel}>{year}</span>
            {cells
              .filter((c) => c.year === year)
              .sort((a, b) => a.month - b.month)
              .map((cell) => {
                const isSelected = selected?.year === cell.year && selected.month === cell.month;
                const description = `${monthLabel(toMonthKey(cell.year, cell.month))}: ${cell.value === null ? 'No coverage information' : `${formatCount(cell.value)} ${unit}`}${cell.isDemo ? ' (demo)' : ''}`;
                return (
                  <button
                    key={cell.month}
                    type="button"
                    className={`${styles.cell} ${isSelected ? styles.cellSelected : ''}`}
                    style={{ background: cell.value === null ? '#E6E8EC' : rampColor(cell.value / max, ACTIVITY_RAMP) }}
                    aria-label={description}
                    aria-pressed={isSelected}
                    title={description}
                    onClick={() => onToggle({ year: cell.year, month: cell.month })}
                  />
                );
              })}
          </div>
        ))}
      </div>
    </div>
  );
}
