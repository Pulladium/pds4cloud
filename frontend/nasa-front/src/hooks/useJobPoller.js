import { useState, useEffect, useRef } from "react";
import { apiFetch } from "../api/apiFetch.js";
import { gatewayUrl } from "../api/gatewayUrl.js";

const POLL_INTERVAL_MS = 2000;
const TERMINAL = new Set(["COMPLETED", "FAILED"]);

export function useJobPoller(jobId) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    setJob(null);
    setError(null);

    if (!jobId) return;

    const poll = async () => {
      try {
        const res = await apiFetch(gatewayUrl(`/api/jobs/${jobId}`));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setError(null);
        setJob(data);
        if (TERMINAL.has(data.status)) {
          clearInterval(intervalRef.current);
        }
      } catch (e) {
        setError(e.message);
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [jobId]);

  return { job, error };
}
