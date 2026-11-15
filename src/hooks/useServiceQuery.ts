import { useCallback, useEffect, useState } from 'react';

export interface ServiceQuery<T> {
  data: T | null;
  /** The key the current data was loaded for. */
  dataKey: string | null;
  status: 'idle' | 'loading' | 'ready' | 'error';
  /** True while refreshing with earlier data still on screen. */
  isUpdating: boolean;
  error: string | null;
  retry: () => void;
}

/**
 * Runs `fetcher` whenever `key` changes. Stale responses are cancelled so an older request
 * can never overwrite a newer one. Previous data stays visible while a refresh is in flight.
 * A null key means "nothing to load".
 */
export function useServiceQuery<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>): ServiceQuery<T> {
  const [state, setState] = useState<{ data: T | null; dataKey: string | null; error: string | null; loadingKey: string | null }>({
    data: null,
    dataKey: null,
    error: null,
    loadingKey: key,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    setState((s) => ({ ...s, loadingKey: key, error: null }));
    fetcher(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, dataKey: key, error: null, loadingKey: null });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : 'Something went wrong while loading data.';
        setState((s) => ({ ...s, error: message, loadingKey: null }));
      });
    return () => controller.abort();
    // `fetcher` is intentionally tied to `key`: callers encode every input in the key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  if (key === null) {
    return { data: null, dataKey: null, status: 'idle', isUpdating: false, error: null, retry };
  }
  const loading = state.loadingKey !== null;
  const status = state.error ? 'error' : state.data ? 'ready' : 'loading';
  return {
    data: state.data,
    dataKey: state.dataKey,
    status,
    isUpdating: loading && state.data !== null,
    error: state.error,
    retry,
  };
}
