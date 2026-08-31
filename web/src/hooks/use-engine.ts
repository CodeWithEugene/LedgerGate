"use client";

import { useCallback, useEffect, useState } from "react";
import { useScope } from "@/components/scope-provider";

/**
 * Fetch from the engine, re-running whenever the scope or a write changes.
 *
 * Deliberately not a data-fetching library. The whole surface is a handful of
 * endpoints against a local server holding a 60-receipt file, and this project
 * has spent a lot of effort keeping its dependency count honest. Adding a
 * cache layer to a page that reloads in single-digit milliseconds would be
 * borrowing complexity against no benefit.
 */
export function useEngine<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): { data: T | null; error: Error | null; loading: boolean; reload: () => void } {
  const { split, policy, revision } = useScope();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetcher()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err);
        setData(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [split, policy, revision, nonce, ...deps]);

  return { data, error, loading, reload };
}
