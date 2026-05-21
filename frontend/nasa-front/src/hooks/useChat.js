import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api/apiFetch.js";

const USER_ID = "dev-user";

export default function useChat(projectId, open) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch history when drawer opens
  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;

    apiFetch(`/api/projects/${projectId}/chat/history`, {
      headers: { "X-User-Id": USER_ID },
    })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setMessages(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });

    return () => { cancelled = true; };
  }, [projectId, open]);

  const sendMessage = useCallback(
    async (content) => {
      if (!content.trim() || loading) return;

      const userMsg = { role: "user", content, created_at: new Date().toISOString() };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);
      setError(null);

      try {
        const r = await apiFetch(`/api/projects/${projectId}/chat/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-User-Id": USER_ID },
          body: JSON.stringify({ content }),
        });
        const json = await r.json();
        if (!r.ok) throw new Error(json.detail || "Failed to send message");
        setMessages((prev) => [...prev, json]);
      } catch (e) {
        setError(e.message);
        // Remove the optimistically added user message on error
        setMessages((prev) => prev.filter((m) => m !== userMsg));
      } finally {
        setLoading(false);
      }
    },
    [projectId, loading]
  );

  const clearHistory = useCallback(async () => {
    await apiFetch(`/api/projects/${projectId}/chat/history`, {
      method: "DELETE",
      headers: { "X-User-Id": USER_ID },
    });
    setMessages([]);
  }, [projectId]);

  return { messages, loading, error, sendMessage, clearHistory };
}
