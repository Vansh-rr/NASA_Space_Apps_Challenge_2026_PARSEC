import { fullDateLabel } from '../../utils/dates';
import { formatCount } from '../../utils/formatters';
import styles from './charts.module.css';

interface TooltipEntry {
  name?: string;
  value?: number | null;
  color?: string;
  dataKey?: string | number;
}

interface Props {
  active?: boolean;
  label?: string | number;
  payload?: TooltipEntry[];
  unit: string;
}

/** Shared tooltip: full date, series name, value and unit. */
export function ChartTooltip({ active, label, payload, unit }: Props) {
  if (!active || !payload || payload.length === 0 || label === undefined) return null;
  return (
    <div className={styles.tooltip}>
      <p className={styles.tooltipDate}>{fullDateLabel(String(label))}</p>
      {payload.map((entry) => (
        <p key={String(entry.dataKey)} className={styles.tooltipRow}>
          <span className={styles.swatch} style={{ background: entry.color }} aria-hidden="true" />
          {entry.name}: <strong>{entry.value == null ? 'Unavailable' : `${formatCount(entry.value)} ${unit}`}</strong>
        </p>
      ))}
    </div>
  );
}
