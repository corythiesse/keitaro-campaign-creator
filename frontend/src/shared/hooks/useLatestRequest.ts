import { useCallback, useMemo, useRef } from "react";

/**
 * Guards asynchronous loads against races: only the answer for the latest
 * request id should be applied to state (StrictMode double effects included).
 */
export function useLatestRequest() {
  const latest = useRef(0);

  const next = useCallback(() => {
    latest.current += 1;
    return latest.current;
  }, []);

  const isLatest = useCallback((id: number) => id === latest.current, []);

  return useMemo(() => ({ next, isLatest }), [next, isLatest]);
}
