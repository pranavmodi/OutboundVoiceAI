export interface QueueInfo {
  Event: string;
  Queue: string;
  Max: number;
  Strategy: string;
  Calls: number;
  Holdtime: number;
  TalkTime: number;
  Completed: number;
  Abandoned: number;
  ServiceLevel: number;
  ServicelevelPerf: number;
  ServicelevelPerf2: number;
  Weight: number;
  AvailableAgents: number;
}

export interface QueueState {
  global_calls_waiting: number;
  global_max_holdtime: number;
  global_agents_available: number;
  outbound_allowed: boolean;
  stable_polls_count: number;
  last_poll_time: string | null;
  ami_connected: boolean;
  queues: QueueInfo[];
}

export interface Patient {
  patient_id: string;
  name: string;
  phone: string;
  language: string;
  order_id: string | null;
  order_created: string | null;
  intake_status: string;
  has_called_in_before: boolean;
  has_abandoned_before: boolean;
  ai_called_before: boolean;
  ai_attempt_count: number;
  human_attempt_count: number;
  total_attempts: number;
  attempt_count: number; // legacy alias for total_attempts
  last_attempt_at: string | null;
  last_outcome: string | null;
  due_by: string | null;
  radflow_status: string | null;
  hl7_sent_at: string | null;
  priority_bucket: number;
}

export interface TranscriptEntry {
  speaker: string;
  text: string;
  timestamp: string;
}

export interface CallLog {
  call_id: string;
  patient_id: string;
  patient_name: string;
  phone: string;
  order_id: string | null;
  priority_bucket: number;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  outcome: string;
  call_status: string;         // "called" | "failed" | "in_progress"
  call_disposition: string;    // "transferred" | "hung_up" | "no_answer" | etc.
  mock_mode: boolean;          // true if this call was redirected to a test number
  voice_provider: string;      // "openai" | "gemini" | "grok"
  transfer_attempted: boolean;
  transfer_success: boolean;
  voicemail_left: boolean;
  sms_sent: boolean;
  preferred_callback_time?: string | null;
  queue_snapshot: QueueState | null;
  transcript: TranscriptEntry[];
  error_code: string | null;
  error_message: string | null;
  recording_sid?: string | null;
  recording_path?: string | null;
  recording_size_bytes?: number | null;
  recording_duration_seconds?: number | null;
  recording_format?: string | null;
  has_recording?: boolean;
}

export interface TodayKpis {
  total_calls: number;
  transferred: number;
  voicemails: number;
  sms: number;
}

export interface Statistics {
  total_calls: number;
  outcomes: Record<string, number>;
  avg_duration_seconds: number;
  transfer_rate: number;
}

export interface SystemStatus {
  queue_state: QueueState;
  outbound_queue_count: number;
  has_active_call: boolean;
  active_call: CallLog | null;
  statistics: Statistics;
}

// WebSocket message types
export type WSMessageType =
  | "initial_state"
  | "call_started"
  | "call_ended"
  | "transcript"
  | "audio"
  | "status"
  | "status_update"
  | "error"
  | "ping"
  | "pong"
  | "queue_update"
  | "dispatcher_event"
  | "settings_updated"
  | "dispatch_call"
  | "dispatch_ack";

export interface WSMessage {
  type: WSMessageType;
  [key: string]: unknown;
}

export interface WSInitialState extends WSMessage {
  type: "initial_state";
  queue_state: QueueState;
  active_call: CallLog | null;
  statistics: Statistics;
}

export interface WSCallStarted extends WSMessage {
  type: "call_started";
  call: CallLog;
}

export interface WSCallEnded extends WSMessage {
  type: "call_ended";
  call: CallLog;
}

export interface WSTranscript extends WSMessage {
  type: "transcript";
  speaker: string;
  text: string;
}

export interface WSAudio extends WSMessage {
  type: "audio";
  data: string; // base64 encoded
}

export interface WSStatus extends WSMessage {
  type: "status" | "status_update";
  status: string;
}

export interface WSError extends WSMessage {
  type: "error";
  message: string;
}

// System Settings Types
export interface HolidayEntry {
  date: string; // YYYY-MM-DD
  name: string;
  recurring: boolean;
}

export interface BusinessHours {
  start_time: string;
  end_time: string;
  enabled: boolean;
  timezone: string;
  days_of_week: number[];  // 0=Mon, 6=Sun
  holidays: HolidayEntry[];
}

export interface QueueThresholds {
  calls_waiting_threshold: number;
  holdtime_threshold_seconds: number;
  stable_polls_required: number;
}

export interface DispatcherSettings {
  poll_interval: number;
  dispatch_timeout: number;
  max_attempts_ordered: number;
  max_attempts_other: number;
  min_hours_between: number;
  verbose_logging?: boolean;
  openai_voice?: string;
  gemini_voice?: string;
  grok_voice?: string;
  call_greeting?: string;
  // Phase 7: parallel-call cap (1 = single-call legacy behavior; ceiling 10).
  max_parallel_calls?: number;
  // Minimum gap (seconds) between consecutive call starts.
  dispatch_pacing_seconds?: number;
}

export interface DailyReportConfig {
  enabled: boolean;
  webhook_url: string;
  hour: number;
  timezone: string;
}

export interface SystemSettings {
  system_enabled: boolean;
  business_hours: BusinessHours;
  queue_thresholds: QueueThresholds;
  dispatcher_settings: DispatcherSettings;
  allow_live_calls: boolean;
  allowed_phones: string[];
  queue_source: string;
  patient_source: string;
  active_scenario_id: string | null;
  call_mode: string;
  mock_mode: boolean;
  mock_phone: string;
  voice_provider: string;
  daily_report: DailyReportConfig;
  can_make_calls: boolean;
  is_within_business_hours: boolean;
}

export interface ApiKeyStatus {
  configured: boolean;
  source: "db" | "env" | "none";
  preview: string;
}

export interface ApiKeysStatusResponse {
  openai: ApiKeyStatus;
  gemini: ApiKeyStatus;
  grok: ApiKeyStatus;
}

export interface TimeSlotStats {
  total: number;
  transferred: number;
  no_answer: number;
  voicemail: number;
  callback: number;
  hung_up: number;
  wrong_number: number;
  technical_error: number;
  disconnected_number: number;
  completed: number;
  transfer_rate: number;
  no_answer_rate: number;
  voicemail_rate: number;
}

export interface DayStats extends TimeSlotStats {
  day: number;
  day_name: string;
}

export interface HourStats extends TimeSlotStats {
  hour: number;
  label: string;
}

export interface TimePerformance {
  days: number;
  timezone: string;
  total_calls: number;
  overall_transfer_rate: number;
  overall_no_answer_rate: number;
  overall_voicemail_rate: number;
  by_day: DayStats[];
  by_hour: HourStats[];
}

export interface ScenarioPatient {
  name: string;
  phone: string;
  language: string;
  has_abandoned_before: boolean;
  has_called_in_before: boolean;
  ai_called_before: boolean;
  attempt_count: number;
}

export interface SimulationScenario {
  id: string;
  label: string;
  description: string;
  is_builtin: boolean;
  ami_connected: boolean;
  queues: QueueInfo[];
  patients: ScenarioPatient[];
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: number;
  call_id: string | null;
  patient_id: string | null;
  patient_name: string;
  order_id: string | null;
  event_type: string;  // radflow | hl7 | sms | email | slack
  action: string;
  status: string;      // success | failed | skipped
  request_summary: string;
  request_payload: Record<string, unknown> | null;
  response_status: number | null;
  error_message: string | null;
  created_at: string | null;
}
