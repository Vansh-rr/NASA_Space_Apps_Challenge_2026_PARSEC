import type { FireObservation } from '../../types/fire';
import { SENSORS } from '../../data/sensors';

type PopupFields = Pick<FireObservation, 'frpMw' | 'observedAt' | 'sensor' | 'isDemo' | 'latitude' | 'longitude'>;

/** Builds popup content with DOM text nodes (never innerHTML) so data cannot inject markup. */
export function buildFirePopup(fire: PopupFields): HTMLElement {
  const root = document.createElement('div');
  root.style.minWidth = '190px';

  const title = document.createElement('strong');
  title.textContent = 'Fire detection';
  title.style.display = 'block';
  title.style.marginBottom = '6px';
  root.append(title);

  const rows: Array<[string, string]> = [
    ['FRP', fire.frpMw === null ? 'Not reported' : `${fire.frpMw.toFixed(1)} MW`],
    ['Observed', formatTimestamp(fire.observedAt)],
    ['Source', SENSORS[fire.sensor]?.label ?? String(fire.sensor)],
    ['Coordinates', `${fire.latitude.toFixed(4)}°, ${fire.longitude.toFixed(4)}°`],
  ];
  if (fire.isDemo) rows.push(['Status', 'Demo data']);

  const list = document.createElement('dl');
  list.style.cssText = 'margin:0;display:grid;grid-template-columns:auto 1fr;gap:3px 12px';
  for (const [label, value] of rows) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    dt.style.color = '#5f6b78';
    const dd = document.createElement('dd');
    dd.textContent = value;
    dd.style.margin = '0';
    list.append(dt, dd);
  }
  root.append(list);
  return root;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })} UTC`;
}
