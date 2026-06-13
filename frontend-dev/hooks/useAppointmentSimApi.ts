"use client";

import { useCallback } from "react";
import type { Appointment, BootstrapResult, Facility, Patient } from "@/types/backfill";

const API_BASE = process.env.NEXT_PUBLIC_BACKFILL_API_URL || "http://localhost:8001";
const SIM = "/api/simulator";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let detail = `API error: ${response.status}`;
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

export function useAppointmentSimApi() {
  const listFacilities = useCallback(() => fetchApi<Facility[]>(`${SIM}/facilities`), []);
  const createFacility = useCallback(
    (name: string, timezone = "America/Los_Angeles") =>
      fetchApi<Facility>(`${SIM}/facilities`, {
        method: "POST",
        body: JSON.stringify({ name, timezone }),
      }),
    []
  );

  const listPatients = useCallback(() => fetchApi<Patient[]>(`${SIM}/patients`), []);
  const createPatient = useCallback(
    (data: {
      name: string;
      phone?: string;
      sms_opt_out?: boolean;
      no_show_flag?: boolean;
      suppressed?: boolean;
    }) =>
      fetchApi<Patient>(`${SIM}/patients`, { method: "POST", body: JSON.stringify(data) }),
    []
  );

  const listAppointments = useCallback(() => fetchApi<Appointment[]>(`${SIM}/appointments`), []);
  const createAppointment = useCallback(
    (data: {
      patient_id: number;
      facility_id: number;
      cpt_code: string;
      scheduled_start_at: string;
    }) =>
      fetchApi<Appointment>(`${SIM}/appointments`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    []
  );

  const loadDemoData = useCallback(
    () => fetchApi<BootstrapResult>(`${SIM}/bootstrap/demo`, { method: "POST" }),
    []
  );

  const clearDemoData = useCallback(
    () => fetchApi<{ message: string; deleted_appointments: number; deleted_patients: number }>(
      `${SIM}/bootstrap/clear-demo`,
      { method: "POST" }
    ),
    []
  );

  const deleteAppointment = useCallback(async (appointmentId: number) => {
    const response = await fetch(`${API_BASE}${SIM}/appointments/${appointmentId}`, {
      method: "DELETE",
    });
    if (!response.ok && response.status !== 204) {
      let detail = `API error: ${response.status}`;
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
  }, []);

  return {
    listFacilities,
    createFacility,
    listPatients,
    createPatient,
    listAppointments,
    createAppointment,
    loadDemoData,
    clearDemoData,
    deleteAppointment,
  };
}
