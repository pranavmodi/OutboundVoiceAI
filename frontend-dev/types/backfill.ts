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

export type BootstrapResult = {
  message: string;
  created: boolean;
  facility_id?: number;
  appointment_to_cancel_id?: number;
};
