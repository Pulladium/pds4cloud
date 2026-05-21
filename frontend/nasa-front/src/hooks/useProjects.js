import { useEffect, useState } from "react";
import { apiFetch } from "../api/apiFetch.js";

const USER_ID = "dev-user";

export default function useProjects(enabled, refreshKey = 0) {
  const [state, setState] = useState({ projects: [], loading: false, error: null });

  useEffect(() => {
    if (!enabled) {
      queueMicrotask(() => setState({ projects: [], loading: false, error: null }));
      return;
    }
    let cancelled = false;

    queueMicrotask(() => {
      if (!cancelled) setState({ projects: [], loading: true, error: null });
    });

    apiFetch("/api/projects", { headers: { "X-User-Id": USER_ID } })
      .then((r) => {
        if (!r.ok) throw new Error(`Server responded with ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        setState({ projects: Array.isArray(data) ? data : data.projects ?? [], loading: false, error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ projects: [], loading: false, error: err.message });
      });

    return () => { cancelled = true; };
  }, [enabled, refreshKey]);

  return state;
}
