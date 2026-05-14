"use client";

import { useCallback } from "react";
import type {
  GateEvaluateRequest,
  GateEvaluateResponse,
  Scenario,
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
    throw new Error(`API error: ${res.status}`);
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

  return { listScenarios, evaluateGate };
}
