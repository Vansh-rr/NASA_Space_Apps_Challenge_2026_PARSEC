import { SENSOR_ORDER, SENSORS } from '../../data/sensors';
import type { ComparisonResponse } from '../../types/comparison';
import { fullDateLabel } from '../../utils/dates';
import { formatCount } from '../../utils/formatters';
import shared from '../../styles/shared.module.css';

/** All dates and sensors in one table, as the non-visual alternative to the three charts. */
export function ComparisonDataTable({ data }: { data: ComparisonResponse }) {
  const dates = data.records.modis.dailyCounts.map((d) => d.date);
  return (
    <details className={shared.details}>
      <summary>View daily detections as a table</summary>
      <div className={shared.tableScroll}>
        <table className={shared.table}>
          <caption className="visually-hidden">Daily detections per sensor record{data.isDemo ? ', demo data' : ''}</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              {SENSOR_ORDER.map((s) => (
                <th key={s} scope="col">
                  {SENSORS[s].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dates.map((date, i) => (
              <tr key={date}>
                <th scope="row">{fullDateLabel(date)}</th>
                {SENSOR_ORDER.map((s) => (
                  <td key={s}>{formatCount(data.records[s].dailyCounts[i]?.count ?? null)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
