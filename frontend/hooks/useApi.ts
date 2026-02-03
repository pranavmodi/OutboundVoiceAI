"use client";

import { useState, useCallback, useMemo } from "react";
import type { SystemStatus, Patient, CallLog, QueueState, SystemSettings, BusinessHours, QueueThresholds, DispatcherSettings, SimulationScenario, ScenarioPatient } from "@/types";

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

  // Scenarios API methods
  const getScenarios = useCallback(async (): Promise<SimulationScenario[]> => {
    try {
      return await fetchApi<SimulationScenario[]>("/api/scenarios");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return [];
    }
  }, []);

  const getScenario = useCallback(async (id: string): Promise<SimulationScenario | null> => {
    try {
      return await fetchApi<SimulationScenario>(`/api/scenarios/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const createScenario = useCallback(async (data: {
    label: string;
    description?: string;
    ami_connected?: boolean;
    queues?: Array<{ Queue: string; Calls?: number; Holdtime?: number; AvailableAgents?: number }>;
    patients?: ScenarioPatient[];
  }): Promise<SimulationScenario | null> => {
    try {
      return await fetchApi<SimulationScenario>("/api/scenarios", {
        method: "POST",
        body: JSON.stringify(data),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const updateScenario = useCallback(async (id: string, data: {
    label?: string;
    description?: string;
    ami_connected?: boolean;
    queues?: Array<{ Queue: string; Calls?: number; Holdtime?: number; AvailableAgents?: number }>;
    patients?: ScenarioPatient[];
  }): Promise<SimulationScenario | null> => {
    try {
      return await fetchApi<SimulationScenario>(`/api/scenarios/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    }
  }, []);

  const deleteScenario = useCallback(async (id: string): Promise<boolean> => {
    try {
      await fetchApi(`/api/scenarios/${id}`, { method: "DELETE" });
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

  const setActiveScenario = useCallback(async (scenarioId: string): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/active-scenario", {
        method: "PUT",
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
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

  const updateDispatcherSettings = useCallback(async (dispatcherSettings: DispatcherSettings): Promise<SystemSettings | null> => {
    try {
      return await fetchApi<SystemSettings>("/api/settings/dispatcher", {
        method: "PUT",
        body: JSON.stringify(dispatcherSettings),
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
    getScenarios,
    getScenario,
    createScenario,
    updateScenario,
    deleteScenario,
    deleteCustomScenarios,
    setActiveScenario,
    getSettings,
    updateSettings,
    setSystemEnabled,
    updateBusinessHours,
    updateQueueThresholds,
    updateDispatcherSettings,
    setAllowLiveCalls,
    updateAllowedPhones,
    setQueueSource,
    setPatientSource,
    getTimezones,
    deleteAllCalls,
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
    getScenarios,
    getScenario,
    createScenario,
    updateScenario,
    deleteScenario,
    deleteCustomScenarios,
    setActiveScenario,
    getSettings,
    updateSettings,
    setSystemEnabled,
    updateBusinessHours,
    updateQueueThresholds,
    updateDispatcherSettings,
    setAllowLiveCalls,
    updateAllowedPhones,
    setQueueSource,
    setPatientSource,
    getTimezones,
    deleteAllCalls,
  ]);
}
