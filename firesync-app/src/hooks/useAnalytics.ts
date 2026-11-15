import { fetchAnalytics } from '../services/analyticsService';
import type { AnalyticsFilters, AnalyticsResponse } from '../types/analytics';
import { useServiceQuery } from './useServiceQuery';

/** One query for cards, charts and map, so every view shares the same applied filters. */
export function useAnalytics(filters: AnalyticsFilters) {
  const key = filters.sensors.length === 0 ? null : `${filters.regionId}|${filters.month}|${[...filters.sensors].sort().join(',')}`;
  return useServiceQuery<AnalyticsResponse>(key, (signal) => fetchAnalytics(filters, signal));
}
