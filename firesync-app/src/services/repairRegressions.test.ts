import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchActivityMatrix, fetchExploreObservations } from './fireData';
import { fetchModelPreview } from './modelPreviewService';
import { buildAnalytics } from './analyticsService';
import { getJson } from './api';

const point = { id: 'a', latitude: 53, longitude: -122, frp_mw: null,
  observed_at: '2023-07-01T12:00:00Z', sensor: 'MODIS', is_demo: false };
const reply = (data: unknown, count?: number) => new Response(JSON.stringify(data),
  { headers: count === undefined ? {} : { 'X-Total-Count': String(count) } });
afterEach(() => vi.unstubAllGlobals());

describe('API paging and provenance regressions', () => {
  it('preserves unknown calendar months', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply([{ year: 2023, month: 7, detections: 20, is_demo: true }])));
    const rows = await fetchActivityMatrix();
    expect(rows).toHaveLength(12);
    expect(rows[0].value).toBeNull();
    expect(rows[6].value).toBe(20);
    expect(rows[6].isDemo).toBe(true);
  });
  it('loads all observation pages and advances the offset', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply([point], 2))
      .mockResolvedValueOnce(reply([{ ...point, id: 'b' }], 2));
    vi.stubGlobal('fetch', fetch);
    const rows = await fetchExploreObservations({ year: 2023, month: 7 });
    expect(rows.map((p) => p.id)).toEqual(['a', 'b']);
    expect(new URL(fetch.mock.calls[1][0]).searchParams.get('offset')).toBe('1');
  });
  it('refuses a truncated observation response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply([point], 2)).mockResolvedValueOnce(reply([], 2)));
    await expect(fetchExploreObservations({ year: 2023, month: 7 })).rejects.toThrow('Incomplete');
  });
  it('uses preview extent outside BC and loads every field page', async () => {
    const metadata = { start_utc: '2024-07-01T00:00:00Z', last_bin_utc: '2024-07-01T01:00:00Z', bbox: [10, 20, 11, 21] };
    const fetch = vi.fn().mockResolvedValueOnce(reply(metadata))
      .mockResolvedValueOnce(reply({ items: [{ cell_id: 'first' }], total: 2 }))
      .mockResolvedValueOnce(reply({ items: [{ cell_id: 'second' }], total: 2 }))
      .mockResolvedValueOnce(reply({ comparison: {} }));
    vi.stubGlobal('fetch', fetch);
    const data = await fetchModelPreview();
    expect(data.items).toHaveLength(2);
    expect(new URL(fetch.mock.calls[1][0]).searchParams.get('bbox')).toBe('10,20,11,21');
    expect(new URL(fetch.mock.calls[2][0]).searchParams.get('offset')).toBe('1');
  });
  it('preserves demo metadata and unavailable KPIs', () => {
    const data = buildAnalytics({ regionId: 'british_columbia', month: '2023-07', sensors: ['harmonized'] },
      { region: 'british_columbia', month: '2023-07', is_demo: true, sensors: [
        { sensor: 'harmonized', detections: 0, mean_frp_mw: null, active_days: 0, daily: [], sample: [], note: 'no run' },
      ] });
    expect(data.isDemo).toBe(true);
    expect(data.metrics.detections.value).toBeNull();
    expect(data.metrics.totalFrp.value).toBeNull();
    expect(data.daily.every((d) => d.dailyFrpMw === null && d.harmonizedDetections === null)).toBe(true);
  });
  it('reports API validation errors and preserves abort signals', async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'invalid date' }), { status: 422 }));
    vi.stubGlobal('fetch', fetch);
    await expect(getJson('/activity', undefined, controller.signal)).rejects.toThrow('API 422: invalid date');
    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
