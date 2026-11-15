const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const twoDecimals = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const UNAVAILABLE = 'Unavailable';

export function formatCount(value: number | null): string {
  return value === null ? UNAVAILABLE : integer.format(value);
}

export function formatOneDecimal(value: number | null): string {
  return value === null ? UNAVAILABLE : oneDecimal.format(value);
}

export function formatTwoDecimals(value: number | null): string {
  return value === null ? UNAVAILABLE : twoDecimals.format(value);
}

export function formatSigned(value: number, digits: number, suffix = ''): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(digits)}${suffix}`;
}

/** 0, 1k, 2k axis labels. */
export function formatCompact(value: number): string {
  if (value >= 1000) return `${Number.isInteger(value / 1000) ? value / 1000 : (value / 1000).toFixed(1)}k`;
  return String(value);
}

/** Linear interpolation across hex colour stops; t in [0, 1]. */
export function rampColor(t: number, stops: string[]): string {
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(scaled));
  const f = scaled - i;
  const a = hexToRgb(stops[i]);
  const b = hexToRgb(stops[i + 1]);
  const mix = a.map((c, k) => Math.round(c + (b[k] - c) * f));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

function hexToRgb(hex: string): number[] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
