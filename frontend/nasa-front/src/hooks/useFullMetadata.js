import { useEffect, useRef, useState } from "react";

const PDS_API = "/api/discovery";

export default function useFullMetadata(lid, { enabled }) {
  const [state, setState] = useState({ data: null, loading: false, error: null });
  const fetchedRef = useRef(null); // stores last-fetched LID; null means not yet fetched

  useEffect(() => {
    if (!enabled || !lid || lid === "null" || lid.includes(":browse:") || fetchedRef.current === lid) return;
    fetchedRef.current = lid;

    const controller = new AbortController();
    setState({ data: null, loading: true, error: null });

    fetch(`${PDS_API}/products/${encodeURIComponent(lid)}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`PDS API ${r.status}`);
        return r.json();
      })
      .then((json) => {
        setState({ data: json, loading: false, error: null });
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          fetchedRef.current = null;
          return;
        }
        setState({ data: null, loading: false, error: err.message || "Unknown error" });
      });

    return () => controller.abort();
  }, [enabled, lid]);

  return state;
}
