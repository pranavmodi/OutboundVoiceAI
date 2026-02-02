"use client";

import { useState, useCallback, useMemo } from "react";
import type { SystemStatus, Patient, CallLog, QueueState, SystemSettings, BusinessHours, QueueThresholds } from "@/types";

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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const applySimulation = useCallback(async (config: any): Promise<any> => {
    setLoading(true);
    setError(null);
    try {
      return await fetchApi("/api/simulation/apply", {
        method: "POST",
        body: JSON.stringify(config),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Settings API methods
  const getSettings = useCallback(async (): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const updateSettings = useCallback(async (settings: Omit<SystemSettings, 'can_make_calls' | 'is_within_business_hours'>): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const setSystemEnabled = useCallback(async (enabled: boolean): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/system-enabled", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const updateBusinessHours = useCallback(async (businessHours: BusinessHours): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/business-hours", {
        method: "PUT",
        body: JSON.stringify(businessHours),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const updateQueueThresholds = useCallback(async (thresholds: QueueThresholds): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/queue-thresholds", {
        method: "PUT",
        body: JSON.stringify(thresholds),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const setAllowLiveCalls = useCallback(async (allowed: boolean): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/allow-live-calls", {
        method: "PUT",
        body: JSON.stringify({ allowed }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const updateAllowedPhones = useCallback(async (phones: string[]): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/allowed-phones", {
        method: "PUT",
        body: JSON.stringify({ phones }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const setQueueSource = useCallback(async (source: string): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/queue-source", {
        method: "PUT",
        body: JSON.stringify({ source }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const setPatientSource = useCallback(async (source: string): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/patient-source", {
        method: "PUT",
        body: JSON.stringify({ source }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const deleteAllCalls = useCallback(async (): Promise<boolean> => {
    try {
      await fetchApi("/api/calls", { method: "DELETE" });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return false;
    }
  }, []);

  const deleteCustomScenarios = useCallback(async (): Promise<boolean> => {
    try {
      await fetchApi("/api/scenarios", { method: "DELETE" });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return false;
    }
  }, []);

  const getTimezones = useCallback(async (): Promise<string[]> => {
    try {
      return await fetchApi<string[]>("/api/settings/timezones");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return [];
    }
  }, []);

  return useMemo(() => ({
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
    applySimulation,
    getSettings,
    updateSettings,
    setSystemEnabled,
    updateBusinessHours,
    updateQueueThresholds,
    setAllowLiveCalls,
    updateAllowedPhones,
    setQueueSource,
    setPatientSource,
    getTimezones,
    deleteAllCalls,
    deleteCustomScenarios,
  }), [
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
    applySimulation,
    getSettings,
    updateSettings,
    setSystemEnabled,
    updateBusinessHours,
    updateQueueThresholds,
    setAllowLiveCalls,
    updateAllowedPhones,
    setQueueSource,
    setPatientSource,
    getTimezones,
    deleteAllCalls,
    deleteCustomScenarios,
  ]);
}
