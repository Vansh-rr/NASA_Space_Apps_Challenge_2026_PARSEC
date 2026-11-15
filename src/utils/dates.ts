const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export const MONTH_SHORT = MONTH_NAMES.map((name) => name.slice(0, 3));

export function parseMonth(month: string): { year: number; month: number } {
  const [year, m] = month.split('-').map(Number);
  return { year, month: m };
}

export function toMonthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`;
}

export function daysInMonth(month: string): number {
  const { year, month: m } = parseMonth(month);
  return new Date(Date.UTC(year, m, 0)).getUTCDate();
}

export function datesOfMonth(month: string): string[] {
  const count = daysInMonth(month);
  return Array.from({ length: count }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`);
}

export function previousMonth(month: string): string {
  const { year, month: m } = parseMonth(month);
  return m === 1 ? toMonthKey(year - 1, 12) : toMonthKey(year, m - 1);
}

/** "2024-08" -> "August 2024" */
export function monthLabel(month: string): string {
  const { year, month: m } = parseMonth(month);
  return `${MONTH_NAMES[m - 1]} ${year}`;
}

/** "2024-08-22" -> "Aug 22" */
export function dayLabel(date: string): string {
  const [, m, d] = date.split('-').map(Number);
  return `${MONTH_SHORT[m - 1]} ${d}`;
}

/** "2024-08-22" -> "August 22, 2024" */
export function fullDateLabel(date: string): string {
  const [y, m, d] = date.split('-').map(Number);
  return `${MONTH_NAMES[m - 1]} ${d}, ${y}`;
}

/** "2024-08" -> "August 1–31, 2024" */
export function monthRangeLabel(month: string): string {
  const { year, month: m } = parseMonth(month);
  return `${MONTH_NAMES[m - 1]} 1–${daysInMonth(month)}, ${year}`;
}

/** Evenly spaced axis ticks: day 1, 6, 11, ... plus the last day of the month. */
export function axisTickDates(dates: string[], step = 5): string[] {
  const ticks = dates.filter((_, i) => i % step === 0);
  const last = dates[dates.length - 1];
  if (ticks[ticks.length - 1] !== last) {
    // Avoid two crowded labels at the end of the axis.
    if (dates.length - 1 - dates.indexOf(ticks[ticks.length - 1]) < 3) ticks.pop();
    ticks.push(last);
  }
  return ticks;
}
