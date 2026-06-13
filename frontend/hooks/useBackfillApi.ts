"use client";

import { useCallback, useMemo } from "react";
import type {
  AgentStatus,
  BackfillSettings,
  BackfillSettingsUpdate,
  Campaign,
  CampaignDetail,
  CampaignListParams,
  CampaignListResponse,
  CancelResult,
  Facility,
  TimelineEntry,
} from "@/types/backfill";

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

/** Cancellation backfill agent: campaigns + cancel trigger only. */
export function useBackfillApi() {
  const health = useCallback(async (): Promise<BackfillHealth | null> => {
    try {
      return await fetchApi<BackfillHealth>("/api/health");
    } catch {
      return null;
    }
  }, []);

  const getAgentStatus = useCallback(async (): Promise<AgentStatus | null> => {
    try {
      return await fetchApi<AgentStatus>("/api/agent/status");
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

  const listCampaigns = useCallback((params?: CampaignListParams) => {
    const search = new URLSearchParams();
    if (params?.started_from) search.set("started_from", params.started_from);
    if (params?.started_to) search.set("started_to", params.started_to);
    if (params?.facility_id) search.set("facility_id", params.facility_id);
    if (params?.status) search.set("status", params.status);
    if (params?.cpt_code) search.set("cpt_code", params.cpt_code);
    if (params?.filled !== undefined) search.set("filled", String(params.filled));
    if (params?.sort) search.set("sort", params.sort);
    if (params?.page) search.set("page", String(params.page));
    if (params?.page_size) search.set("page_size", String(params.page_size));
    const qs = search.toString();
    return fetchApi<CampaignListResponse>(`/api/campaigns${qs ? `?${qs}` : ""}`);
  }, []);

  const listFacilities = useCallback(
    () => fetchApi<Facility[]>("/api/facilities"),
    []
  );
  const getCampaign = useCallback(
    (id: number) => fetchApi<CampaignDetail>(`/api/campaigns/${id}`),
    []
  );

  const getCampaignTimeline = useCallback(
    (id: number) => fetchApi<TimelineEntry[]>(`/api/campaigns/${id}/timeline`),
    []
  );

  const stopCampaign = useCallback(
    (id: number) =>
      fetchApi<CampaignDetail>(`/api/campaigns/${id}/stop`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    []
  );

  const getSettings = useCallback(() => fetchApi<BackfillSettings>("/api/settings"), []);

  const putSettings = useCallback(
    (body: BackfillSettingsUpdate) =>
      fetchApi<BackfillSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    []
  );

  return useMemo(
    () => ({
      health,
      getAgentStatus,
      cancelAppointment,
      listCampaigns,
      listFacilities,
      getCampaign,
      getCampaignTimeline,
      stopCampaign,
      getSettings,
      putSettings,
    }),
    [
      health,
      getAgentStatus,
      cancelAppointment,
      listCampaigns,
      listFacilities,
      getCampaign,
      getCampaignTimeline,
      stopCampaign,
      getSettings,
      putSettings,
    ]
  );
}
