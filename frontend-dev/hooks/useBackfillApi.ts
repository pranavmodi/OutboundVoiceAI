"use client";

import { useCallback } from "react";
import type { CancelResult } from "@/types/backfill";

const API_BASE = process.env.NEXT_PUBLIC_BACKFILL_API_URL || "http://localhost:8001";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let detail = `Backfill API error: ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json();
}

export type BackfillHealth = { status: string; service: string };

export function useBackfillApi() {
  const health = useCallback(async (): Promise<BackfillHealth | null> => {
    try {
      return await fetchApi<BackfillHealth>("/api/health");
    } catch {
      return null;
    }
  }, []);

  const cancelAppointment = useCallback(
    (appointmentId: number) =>
      fetchApi<CancelResult>(`/api/simulator/appointments/${appointmentId}/cancel`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    []
  );

  return { health, cancelAppointment };
}
