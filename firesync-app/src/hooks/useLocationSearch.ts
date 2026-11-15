import { useCallback, useEffect, useRef, useState } from 'react';
import { DEMO_PLACES, geocode } from '../services/geocoding';
import type { SearchMode, SelectedLocation } from '../types/fire';
import { parseCoordinates } from '../utils/metrics';

interface SearchState {
  status: 'idle' | 'loading';
  error: string | null;
  /** Several matches: the user picks one. */
  choices: SelectedLocation[];
}

const IDLE: SearchState = { status: 'idle', error: null, choices: [] };

/** Resolves a place name or coordinate pair. A newer search always cancels an older one. */
export function useLocationSearch(onResolved: (location: SelectedLocation) => void) {
  const [state, setState] = useState<SearchState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState(IDLE);
  }, []);

  const search = useCallback(
    async (mode: SearchMode, query: string) => {
      controllerRef.current?.abort();

      if (mode === 'coordinates') {
        const result = parseCoordinates(query);
        if (!result.ok) {
          setState({ ...IDLE, error: result.error });
          return;
        }
        setState(IDLE);
        onResolved({
          latitude: result.latitude,
          longitude: result.longitude,
          label: `${result.latitude.toFixed(4)}, ${result.longitude.toFixed(4)}`,
        });
        return;
      }

      if (!query.trim()) {
        setState({ ...IDLE, error: 'Enter a place name to search.' });
        return;
      }

      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: 'loading', error: null, choices: [] });
      try {
        const matches = await geocode(query, controller.signal);
        if (controller.signal.aborted) return;
        if (matches.length === 0) {
          const supported = DEMO_PLACES.map((p) => p.label.split(',')[0]).join(', ');
          setState({ ...IDLE, error: `No match for "${query.trim()}". The demo recognises: ${supported}.` });
        } else if (matches.length === 1) {
          setState(IDLE);
          onResolved(matches[0]);
        } else {
          setState({ status: 'idle', error: null, choices: matches });
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setState({ ...IDLE, error: 'The place search failed. Please try again.' });
      }
    },
    [onResolved],
  );

  const choose = useCallback(
    (location: SelectedLocation) => {
      setState(IDLE);
      onResolved(location);
    },
    [onResolved],
  );

  return { ...state, search, choose, reset };
}
