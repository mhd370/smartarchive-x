"use client";
import { useCallback, useEffect, useState } from "react";
import { get } from "./api";

/** Fetch a resource; `poll` (ms) refreshes it silently, without clearing what is on screen. */
export function useApi<T>(path: string | null, poll?: number | false) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    if (!path) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(""); setData(undefined);
    get<T>(path, controller.signal).then(value => {
      if (!controller.signal.aborted) setData(value);
    }).catch((failure: Error) => {
      if (!controller.signal.aborted) setError(failure.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, version]);
  useEffect(() => {
    if (!path || !poll) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      get<T>(path, controller.signal).then(value => { if (!controller.signal.aborted) { setData(value); setError(""); } })
        .catch(() => undefined);
    }, poll);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [path, poll]);
  return { data, error, loading, reload };
}
