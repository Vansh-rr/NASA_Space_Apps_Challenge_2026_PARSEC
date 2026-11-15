import { SENSOR_ORDER, SENSORS } from '../../data/sensors';
import type { DailyAnalytics } from '../../types/analytics';
import type { SensorId } from '../../types/fire';
import { fullDateLabel } from '../../utils/dates';
import { formatCount } from '../../utils/formatters';
import shared from '../../styles/shared.module.css';

const KEY: Record<SensorId, keyof DailyAnalytics> = {
  modis: 'modisDetections',
  viirs: 'viirsDetections',
  harmonized: 'harmonizedDetections',
};

/** Tabular alternative to both charts, so hover is never the only way to read values. */
export function ChartDataTable({ daily, sensors }: { daily: DailyAnalytics[]; sensors: SensorId[] }) {
  const active = SENSOR_ORDER.filter((s) => sensors.includes(s));
  return (
    <details className={shared.details}>
      <summary>View chart data as a table</summary>
      <div className={shared.tableScroll}>
        <table className={shared.table}>
          <caption className="visually-hidden">Daily FRP and detections, demo data</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Daily FRP (MW)</th>
              <th scope="col">Trend, 3-day average (MW)</th>
              {active.map((s) => (
                <th key={s} scope="col">
                  {SENSORS[s].label} detections
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {daily.map((d) => (
              <tr key={d.date}>
                <th scope="row">{fullDateLabel(d.date)}</th>
                <td>{formatCount(d.dailyFrpMw)}</td>
                <td>{formatCount(d.trendFrpMw)}</td>
                {active.map((s) => (
                  <td key={s}>{formatCount(d[KEY[s]] as number | null)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
