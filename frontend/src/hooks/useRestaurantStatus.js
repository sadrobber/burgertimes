import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export function useRestaurantStatus(pollMs = 60000) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const { data } = await apiClient.get("/restaurant/status");
        if (!cancelled) setStatus(data);
      } catch (e) {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollMs]);

  return { status, loading };
}
