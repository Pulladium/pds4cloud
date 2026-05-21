import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/apiFetch.js";

const REFRESH_INTERVAL_S = 30;

export default function useLangSmithStats() {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL_S);
  const countdownRef = useRef(countdown);
  countdownRef.current = countdown;

  const fetchStats = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    apiFetch("/api/langsmith/stats")
      .then((r) => {
        if (!r.ok) return r.json().then((j) => { throw new Error(j.detail || `HTTP ${r.status}`); });
        return r.json();
      })
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e) => setState({ data: null, loading: false, error: e.message }));
    setCountdown(REFRESH_INTERVAL_S);
  }, []);

  useEffect(() => {
    fetchStats();
    const refreshTimer = setInterval(fetchStats, REFRESH_INTERVAL_S * 1000);
    const tickTimer = setInterval(
      () => setCountdown((c) => (c > 0 ? c - 1 : REFRESH_INTERVAL_S)),
      1000,
    );
    return () => {
      clearInterval(refreshTimer);
      clearInterval(tickTimer);
    };
  }, [fetchStats]);

  return { ...state, countdown, refresh: fetchStats };
}
