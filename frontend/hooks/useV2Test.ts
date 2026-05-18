"use client";

import { useCallback } from "react";
import type {
  EndCallResponse,
  GateEvaluateRequest,
  GateEvaluateResponse,
  RecentRunSummary,
  Scenario,
  StartCallResponse,
} from "@/types/v2-test";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    // Try to surface the FastAPI error detail when present.
    let detail = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = String(body.detail);
      }
    } catch {
      // ignore body-parse failures; fall back to the status code
    }
    throw new Error(detail);
  }
  return res.json();
}

export function useV2Test() {
  const listScenarios = useCallback(async (): Promise<Scenario[]> => {
    const data = await fetchApi<{ scenarios: Scenario[] }>("/api/v2-test/scenarios");
    return data.scenarios;
  }, []);

  const evaluateGate = useCallback(
    async (req: GateEvaluateRequest): Promise<GateEvaluateResponse> => {
      return fetchApi<GateEvaluateResponse>("/api/v2-test/gate-evaluate", {
        method: "POST",
        body: JSON.stringify(req),
      });
    },
    []
  );

  const startCall = useCallback(
    async (scenario: Scenario): Promise<StartCallResponse> => {
      return fetchApi<StartCallResponse>("/api/v2-test/start-call", {
        method: "POST",
        body: JSON.stringify(scenario),
      });
    },
    []
  );

  const endCall = useCallback(
    async (callId: string): Promise<EndCallResponse> => {
      return fetchApi<EndCallResponse>(`/api/v2-test/end-call/${callId}`, {
        method: "POST",
      });
    },
    []
  );

  const listRecentRuns = useCallback(
    async (limit: number = 20): Promise<RecentRunSummary[]> => {
      const data = await fetchApi<{ runs: RecentRunSummary[] }>(
        `/api/v2-test/recent-runs?limit=${limit}`
      );
      return data.runs;
    },
    []
  );

  return { listScenarios, evaluateGate, startCall, endCall, listRecentRuns };
}
