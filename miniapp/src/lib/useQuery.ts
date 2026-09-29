import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from './api';

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useQuery<T>(loader: () => Promise<T>, key = ''): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const ref = useRef(loader);
  ref.current = loader;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    ref
      .current()
      .then((result) => {
        if (active) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((exception: unknown) => {
        if (!active) return;
        setError(exception instanceof ApiError ? exception.message : 'Не удалось загрузить данные');
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, loading, error, reload };
}

export function useAction(): {
  busy: boolean;
  error: string | null;
  notice: string | null;
  run: (action: () => Promise<void>, successMessage?: string) => Promise<boolean>;
  reset: () => void;
} {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const run = useCallback(async (action: () => Promise<void>, successMessage?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      if (successMessage) setNotice(successMessage);
      return true;
    } catch (exception) {
      setError(exception instanceof ApiError ? exception.message : 'Действие не выполнено');
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setNotice(null);
  }, []);

  return { busy, error, notice, run, reset };
}
