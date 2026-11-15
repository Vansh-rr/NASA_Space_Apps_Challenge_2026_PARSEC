import { fetchComparison } from '../services/comparisonService';
import type { ComparisonResponse } from '../types/comparison';
import { useServiceQuery } from './useServiceQuery';

export function useComparisonData(regionId: string, month: string) {
  return useServiceQuery<ComparisonResponse>(`${regionId}|${month}`, (signal) => fetchComparison(regionId, month, signal));
}
