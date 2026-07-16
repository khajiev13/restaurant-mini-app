import { useCallback, useEffect, useRef, useState } from 'react';

export function useVisiblePolling<T>(
  load: () => Promise<T>,
  intervalMs: number,
  requestKey: unknown,
) {
  const loadRef = useRef(load);
  loadRef.current = load;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const mountedRef = useRef(false);
  const generationRef = useRef(0);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const activeRequestKeyRef = useRef<unknown>(undefined);
  const hasActiveRequestKeyRef = useRef(false);

  const refresh = useCallback((): Promise<void> => {
    if (inFlightRef.current) {
      return inFlightRef.current;
    }

    const generation = generationRef.current;
    const request = (async () => {
      try {
        const next = await loadRef.current();
        if (!mountedRef.current || generation !== generationRef.current) {
          return;
        }
        setData(next);
        setError(null);
      } catch (cause) {
        if (!mountedRef.current || generation !== generationRef.current) {
          return;
        }
        setError(cause);
      } finally {
        if (mountedRef.current && generation === generationRef.current) {
          setLoading(false);
        }
      }
    })();
    const task = request.finally(() => {
      if (inFlightRef.current === task) {
        inFlightRef.current = null;
      }
    });
    inFlightRef.current = task;
    return task;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const requestKeyChanged =
      !hasActiveRequestKeyRef.current ||
      !Object.is(activeRequestKeyRef.current, requestKey);
    if (requestKeyChanged) {
      hasActiveRequestKeyRef.current = true;
      activeRequestKeyRef.current = requestKey;
      generationRef.current += 1;
      inFlightRef.current = null;
      setData(null);
      setError(null);
      setLoading(true);
    }
    let timer: number | undefined;

    const stop = () => {
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
      timer = undefined;
    };
    const start = () => {
      stop();
      if (document.visibilityState !== 'hidden') {
        timer = window.setInterval(() => {
          void refresh();
        }, intervalMs);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        stop();
      } else {
        void refresh();
        start();
      }
    };

    void refresh();
    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mountedRef.current = false;
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [intervalMs, refresh, requestKey]);

  return { data, loading, error, refresh };
}
