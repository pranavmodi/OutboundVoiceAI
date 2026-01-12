"use client";

import { useState, useCallback } from "react";
import type { SystemStatus, Patient, CallLog, QueueState } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export function useApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getStatus = useCallback(async (): Promise<SystemStatus | null> => {
    setLoading(true);
    setError(null);
    try {
      return await fetchApi<SystemStatus>("/api/status");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const getQueueState = useCallback(async (): Promise<QueueState | null> => {
    try {
      return await fetchApi<QueueState>("/api/queue");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const getPatients = useCallback(async (): Promise<Patient[]> => {
    try {
      const data = await fetchApi<{ patients: Patient[] }>("/api/patients");
      return data.patients;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return [];
    }
  }, []);

  const getOutboundQueue = useCallback(async (): Promise<Patient[]> => {
    try {
      const data = await fetchApi<{ queue: Patient[] }>("/api/patients/queue");
      return data.queue;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return [];
    }
  }, []);

  const getCalls = useCallback(async (limit: number = 50): Promise<CallLog[]> => {
    try {
      const data = await fetchApi<{ calls: CallLog[] }>(`/api/calls?limit=${limit}`);
      return data.calls;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return [];
    }
  }, []);

  const getCall = useCallback(async (callId: string): Promise<CallLog | null> => {
    try {
      return await fetchApi<CallLog>(`/api/calls/${callId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const simulateBusyQueue = useCallback(async (): Promise<QueueState | null> => {
    try {
      const data = await fetchApi<{ queue_state: QueueState }>("/api/queue/simulate/busy", {
        method: "POST",
      });
      return data.queue_state;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const simulateQuietQueue = useCallback(async (): Promise<QueueState | null> => {
    try {
      const data = await fetchApi<{ queue_state: QueueState }>("/api/queue/simulate/quiet", {
        method: "POST",
      });
      return data.queue_state;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const simulateAmiFailure = useCallback(async (): Promise<QueueState | null> => {
    try {
      const data = await fetchApi<{ queue_state: QueueState }>("/api/queue/simulate/ami-failure", {
        method: "POST",
      });
      return data.queue_state;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const simulateAmiRecovery = useCallback(async (): Promise<QueueState | null> => {
    try {
      const data = await fetchApi<{ queue_state: QueueState }>("/api/queue/simulate/ami-recovery", {
        method: "POST",
      });
      return data.queue_state;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const resetPatients = useCallback(async (): Promise<void> => {
    try {
      await fetchApi("/api/patients/reset", { method: "POST" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }, []);

  return {
    loading,
    error,
    getStatus,
    getQueueState,
    getPatients,
    getOutboundQueue,
    getCalls,
    getCall,
    simulateBusyQueue,
    simulateQuietQueue,
    simulateAmiFailure,
    simulateAmiRecovery,
    resetPatients,
  };
}
