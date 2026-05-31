export type Facility = {
  id: number;
  name: string;
  timezone: string;
};

export type Patient = {
  id: number;
  name: string;
  phone: string | null;
  sms_opt_out: boolean;
  no_show_flag: boolean;
  suppressed: boolean;
};

export type Appointment = {
  id: number;
  patient_id: number;
  patient_name: string | null;
  facility_id: number;
  facility_name: string | null;
  cpt_code: string;
  status: string;
  scheduled_start_at: string;
  cancelled_at: string | null;
};

export type CancelResult = {
  appointment_id: number;
  cancelled: boolean;
  campaign_created: boolean;
  campaign_id: number | null;
  message: string;
};

export type Campaign = {
  id: number;
  cancelled_appointment_id: number;
  cancelled_patient_id: number;
  cancelled_patient_name: string | null;
  facility_id: number;
  facility_name: string | null;
  cpt_code: string;
  open_slot_start_at: string;
  cancellation_at: string;
  campaign_status: string;
  started_at: string;
  ended_at: string | null;
  closed_reason: string | null;
  filled_by_patient_id: number | null;
  filled_by_patient_name: string | null;
  filled_by_appointment_id: number | null;
  candidate_count: number;
  eligible_count: number;
};

export type CampaignListParams = {
  started_from?: string;
  started_to?: string;
  facility_id?: string;
  status?: string;
  cpt_code?: string;
  filled?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
};

export type CampaignListResponse = {
  items: Campaign[];
  total: number;
  page: number;
  page_size: number;
};

export type Candidate = {
  id: number;
  patient_id: number;
  patient_name: string | null;
  appointment_id: number;
  scheduled_appointment_at: string;
  rank_order: number;
  eligibility_status: string;
  exclusion_reason: string | null;
};

export type CampaignDetail = Campaign & {
  candidates: Candidate[];
};

export type TimelineEntry = {
  id: number;
  attempted_at: string;
  action_type: string;
  patient_id: number | null;
  patient_name: string | null;
  channel: string;
  wave_number: number | null;
  outcome: string | null;
  provider_message_id: string | null;
};

export type BootstrapResult = {
  message: string;
  created: boolean;
  facility_id?: number;
  appointment_to_cancel_id?: number;
};

/** Agent settings — mirrors GET/PUT /api/settings */
export type BackfillSettings = {
  id: number;
  enabled: boolean;
  minimum_cancellation_notice_hours: number;
  sms_batch_size_per_wave: number;
  delay_between_waves_minutes: number;
  max_waves: number;
  ai_call_escalation_enabled: boolean;
  ai_call_quantity_per_wave: number;
  allowed_contact_days: string;
  contact_window_start: string;
  contact_window_end: string;
  contact_window_timezone: string;
  use_shared_holiday_calendar: boolean;
  agent_blackout_dates: string[] | null;
  same_facility_required: boolean;
  same_cpt_required: boolean;
  exclude_no_show_enabled: boolean;
  campaign_timeout_minutes: number | null;
  late_response_closeout_enabled: boolean;
  allowed_sms_template_id: number | null;
  allowed_voice_template_id: number | null;
  closeout_message_template_id: number | null;
  updated_at: string;
};

export type BackfillSettingsUpdate = Omit<BackfillSettings, "id" | "updated_at">;

export type AgentStatus = {
  enabled: boolean;
  status: string;
  service: string;
};
