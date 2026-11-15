import type { FireObservation, SensorId } from '../types/fire';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export interface ApiObservation {
  id: string | number;
  latitude: number;
  longitude: number;
  frp_mw: number | null;
  observed_at: string;
  sensor: string;
  is_demo?: boolean;
}

export async function getJson<T>(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  return (await getJsonPage<T>(path, params, signal)).data;
}

export async function getJsonPage<T>(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
  signal?: AbortSignal,
): Promise<{ data: T; headers: Headers }> {
  const url = new URL(path.startsWith('/') ? `${API_BASE}${path}` : `${API_BASE}/${path}`,
    globalThis.location?.origin ?? 'http://localhost');
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const res = await fetch(url.toString(), { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') {
        detail = body.detail;
      } else if (body && body.detail !== undefined) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // ignore non-json error body
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return { data: await res.json() as T, headers: res.headers };
}

export function toObservation(p: ApiObservation): FireObservation {
  return {
    id: String(p.id),
    latitude: p.latitude,
    longitude: p.longitude,
    frpMw: p.frp_mw ?? null,
    observedAt: p.observed_at,
    sensor: p.sensor.toLowerCase() as SensorId,
    isDemo: Boolean(p.is_demo),
  };
}
