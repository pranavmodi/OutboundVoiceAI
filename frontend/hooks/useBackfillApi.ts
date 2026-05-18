"use client";

import { useCallback } from "react";

const BACKFILL_API_BASE =
  process.env.NEXT_PUBLIC_BACKFILL_API_URL || "http://localhost:8001";

async function fetchBackfillApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BACKFILL_API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`Backfill API error: ${response.status}`);
  }
  return response.json();
}

export type BackfillHealth = { status: string; service: string };

export function useBackfillApi() {
  const health = useCallback(async (): Promise<BackfillHealth | null> => {
    try {
      return await fetchBackfillApi<BackfillHealth>("/api/health");
    } catch {
      return null;
    }
  }, []);

  return { health };
}
