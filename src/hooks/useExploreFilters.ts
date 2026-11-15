import { useCallback, useState } from 'react';
import type { ExploreFilters, Period, SearchMode, SelectedLocation } from '../types/fire';

/** Draft search input plus the applied period and location for the Explore page. */
export function useExploreFilters() {
  const [filters, setFilters] = useState<ExploreFilters>({
    mode: 'place',
    query: '',
    selectedPeriod: null,
    selectedLocation: null,
  });

  const setMode = useCallback((mode: SearchMode) => setFilters((f) => (f.mode === mode ? f : { ...f, mode, query: '' })), []);
  const setQuery = useCallback((query: string) => setFilters((f) => ({ ...f, query })), []);
  const setLocation = useCallback(
    (selectedLocation: SelectedLocation | null) => setFilters((f) => ({ ...f, selectedLocation })),
    [],
  );
  /** Selecting the active period again clears it. */
  const togglePeriod = useCallback(
    (period: Period) =>
      setFilters((f) => {
        const same = f.selectedPeriod?.year === period.year && f.selectedPeriod?.month === period.month;
        return { ...f, selectedPeriod: same ? null : period };
      }),
    [],
  );
  const clearPeriod = useCallback(() => setFilters((f) => ({ ...f, selectedPeriod: null })), []);

  return { filters, setMode, setQuery, setLocation, togglePeriod, clearPeriod };
}
