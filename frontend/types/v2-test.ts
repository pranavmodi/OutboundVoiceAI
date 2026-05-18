// Shapes mirror app/api/v2_test.py — keep in sync if the backend changes.

export type IntakeCategory = "DEMOGRAPHICS" | "PRESCREEN" | "PHOTO_ID" | "SIGNED_LIEN";

export type Modality = "RADIATION" | "MR_NON_CONTRAST" | "MR_CONTRAST";

export interface ScenarioPatient {
  name: string;
  tenant_id: string;
  order_id: string;
  dob_on_order: string; // YYYY-MM-DD
}

export interface OutstandingTaskSpec {
  category: IntakeCategory;
  field_id: string;
}

export interface FlagOverrides {
  mode_voice_capture: boolean;
  mode_portal_copilot: boolean;
  multi_call_resume: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  patient: ScenarioPatient;
  expected_patient_dob: string;
  modality: Modality;
  outstanding_tasks: OutstandingTaskSpec[];
  flag_overrides: FlagOverrides;
  expected_handoff_reason?: string | null;
  expected_behavior?: string | null;
}

export interface GateOverlay {
  master_enabled: boolean;
  tenant_allowlist: string[];
  order_canary_pct: number;
}

export interface GateEvaluateRequest {
  order_id: string | null;
  tenant_id: string | null;
  overlay: GateOverlay;
}

export interface GateEvaluateResponse {
  eligible: boolean;
  reason: string;
  canary_bucket: number | null;
}

export interface StartCallResponse {
  call_id: string;
}

export interface EndCallResponse {
  ended: boolean;
}

export interface RecentRunSummary {
  call_id: string;
  patient_name: string;
  order_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  outcome: string;
  duration_seconds: number;
}

export interface RecentRunsResponse {
  runs: RecentRunSummary[];
}
