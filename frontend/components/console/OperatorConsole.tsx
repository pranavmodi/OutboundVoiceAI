"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Power,
  Clock,
  SlidersHorizontal,
  CheckCircle,
  XCircle,
  Save,
  ShieldAlert,
  Phone,
  PhoneCall,
  Monitor,
  Plus,
  Trash2,
  Radio,
  Users,
} from "lucide-react";
import type { SystemSettings, BusinessHours, QueueThresholds } from "@/types";

interface OperatorConsoleProps {
  settings: SystemSettings | null;
  timezones: string[];
  callMode: string;
  onCallModeChange: (mode: string) => void;
  onSetSystemEnabled: (enabled: boolean) => Promise<void>;
  onUpdateBusinessHours: (businessHours: BusinessHours) => Promise<void>;
  onUpdateQueueThresholds: (thresholds: QueueThresholds) => Promise<void>;
  onSetAllowLiveCalls: (allowed: boolean) => Promise<void>;
  onUpdateAllowedPhones: (phones: string[]) => Promise<void>;
  onSetQueueSource: (source: string) => Promise<void>;
  onSetPatientSource: (source: string) => Promise<void>;
}

export function OperatorConsole({
  settings,
  timezones,
  callMode,
  onCallModeChange,
  onSetSystemEnabled,
  onUpdateBusinessHours,
  onUpdateQueueThresholds,
  onSetAllowLiveCalls,
  onUpdateAllowedPhones,
  onSetQueueSource,
  onSetPatientSource,
}: OperatorConsoleProps) {
  const [businessHoursForm, setBusinessHoursForm] = useState<BusinessHours>({
    start_time: "08:00",
    end_time: "17:00",
    enabled: false,
    timezone: "America/New_York",
  });

  const [thresholdsForm, setThresholdsForm] = useState<QueueThresholds>({
    calls_waiting_threshold: 1,
    holdtime_threshold_seconds: 30,
    stable_polls_required: 3,
  });

  const [newPhone, setNewPhone] = useState("");

  useEffect(() => {
    if (settings) {
      setBusinessHoursForm(settings.business_hours);
      setThresholdsForm(settings.queue_thresholds);
    }
  }, [settings]);

  const handleAddPhone = async () => {
    const phone = newPhone.trim();
    if (!phone || !settings) return;
    if (settings.allowed_phones.includes(phone)) {
      setNewPhone("");
      return;
    }
    await onUpdateAllowedPhones([...settings.allowed_phones, phone]);
    setNewPhone("");
  };

  const handleRemovePhone = async (phone: string) => {
    if (!settings) return;
    await onUpdateAllowedPhones(settings.allowed_phones.filter((p) => p !== phone));
  };

  const handleBusinessHoursSubmit = async () => {
    await onUpdateBusinessHours(businessHoursForm);
  };

  const handleThresholdsSubmit = async () => {
    await onUpdateQueueThresholds(thresholdsForm);
  };

  if (!settings) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* System Control */}
      <div className="flex items-center justify-between rounded-lg border p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Power className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium">System Status</p>
            <p className="text-xs text-muted-foreground">
              {settings.system_enabled
                ? "Active — calls can be placed"
                : "Disabled — no calls will be placed"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {settings.can_make_calls ? (
            <Badge variant="success" className="flex items-center gap-1">
              <CheckCircle className="h-3 w-3" />
              Ready
            </Badge>
          ) : (
            <Badge variant="outline" className="flex items-center gap-1 text-muted-foreground">
              <XCircle className="h-3 w-3" />
              Blocked
            </Badge>
          )}
          <Switch
            checked={settings.system_enabled}
            onCheckedChange={onSetSystemEnabled}
          />
        </div>
      </div>

      <Separator />

      {/* Call Mode */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <PhoneCall className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Call Mode</h4>
        </div>
        <p className="text-xs text-muted-foreground">
          Choose how outbound calls are placed. Web mode uses the browser microphone to simulate the patient. Twilio mode dials a real phone number via Twilio and streams audio between the phone and the AI.
        </p>
        <div className="flex items-center gap-4">
          <Select value={callMode} onValueChange={onCallModeChange}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="web">
                <span className="flex items-center gap-2">
                  <Monitor className="h-4 w-4" />
                  Web (Browser Audio)
                </span>
              </SelectItem>
              <SelectItem value="twilio">
                <span className="flex items-center gap-2">
                  <PhoneCall className="h-4 w-4" />
                  Twilio (Real Phone Call)
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          {callMode === "twilio" && (
            <Badge variant="outline" className="text-orange-600 border-orange-600">
              Real calls — charges apply
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {callMode === "web"
            ? "Audio streams between your browser and OpenAI. You speak as the patient through your microphone."
            : "Twilio dials the patient's phone number. Audio streams between the phone line and OpenAI. The browser still shows transcripts and controls."}
        </p>
      </div>

      <Separator />

      {/* Queue Source */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Queue Source</h4>
        </div>
        <p className="text-xs text-muted-foreground">
          Choose where queue data comes from. Simulation uses a mock provider you can control manually. Live connects to the FreePBX queue status endpoint for real-time data.
        </p>
        <div className="flex items-center gap-4">
          <Select value={settings.queue_source} onValueChange={onSetQueueSource}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="simulation">
                <span className="flex items-center gap-2">
                  <Monitor className="h-4 w-4" />
                  Simulation
                </span>
              </SelectItem>
              <SelectItem value="live">
                <span className="flex items-center gap-2">
                  <Radio className="h-4 w-4" />
                  Live FreePBX
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          {settings.queue_source === "live" && (
            <Badge variant="outline" className="text-blue-600 border-blue-600">
              Live data
            </Badge>
          )}
        </div>
      </div>

      <Separator />

      {/* Patient Source */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Patient Source</h4>
        </div>
        <p className="text-xs text-muted-foreground">
          Choose where patient call list data comes from. Simulation uses sample patients you can control manually. Live connects to the RadFlow CallListData API for real patient data.
        </p>
        <div className="flex items-center gap-4">
          <Select value={settings.patient_source} onValueChange={onSetPatientSource}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="simulation">
                <span className="flex items-center gap-2">
                  <Monitor className="h-4 w-4" />
                  Simulation
                </span>
              </SelectItem>
              <SelectItem value="live">
                <span className="flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  Live RadFlow
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          {settings.patient_source === "live" && (
            <Badge variant="outline" className="text-blue-600 border-blue-600">
              Live data
            </Badge>
          )}
        </div>
      </div>

      <Separator />

      {/* Live Calls Safeguard */}
      <div className="space-y-4 rounded-lg border border-orange-200 bg-orange-50/50 dark:border-orange-900 dark:bg-orange-950/20 p-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-orange-600 dark:text-orange-400" />
          <h4 className="text-sm font-medium">Live Call Safeguards</h4>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="allow-live-calls" className="text-sm">Allow Live Twilio Calls</Label>
            <p className="text-xs text-muted-foreground">
              When off, only web-simulated calls are allowed
            </p>
          </div>
          <Switch
            id="allow-live-calls"
            checked={settings.allow_live_calls}
            onCheckedChange={onSetAllowLiveCalls}
          />
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">
            Phone Number Allowlist
          </Label>
          <p className="text-xs text-muted-foreground">
            Only these numbers can be dialed via Twilio. Empty list blocks all calls.
          </p>
          <div className="flex gap-2">
            <Input
              placeholder="+15551234567"
              value={newPhone}
              onChange={(e) => setNewPhone(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleAddPhone(); }}
              className="h-9"
            />
            <Button size="sm" variant="outline" onClick={handleAddPhone} disabled={!newPhone.trim()}>
              <Plus className="h-3 w-3 mr-1" />
              Add
            </Button>
          </div>
          {settings.allowed_phones.length > 0 ? (
            <div className="flex flex-wrap gap-2 pt-1">
              {settings.allowed_phones.map((phone) => (
                <Badge key={phone} variant="secondary" className="flex items-center gap-1.5 pl-2 pr-1 py-1">
                  <Phone className="h-3 w-3" />
                  {phone}
                  <button
                    onClick={() => handleRemovePhone(phone)}
                    className="ml-1 rounded-full p-0.5 hover:bg-destructive/20 hover:text-destructive transition-colors"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-xs text-orange-600 dark:text-orange-400 font-medium pt-1">
              No numbers allowed — all Twilio calls are blocked
            </p>
          )}
        </div>
      </div>

      <Separator />

      {/* Business Hours + Queue Thresholds side by side */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Business Hours */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium">Business Hours</h4>
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="business-hours-enabled" className="text-sm">Enforce hours</Label>
            <Switch
              id="business-hours-enabled"
              checked={businessHoursForm.enabled}
              onCheckedChange={(checked) =>
                setBusinessHoursForm({ ...businessHoursForm, enabled: checked })
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="start-time" className="text-xs text-muted-foreground">Start</Label>
              <Input
                id="start-time"
                type="time"
                value={businessHoursForm.start_time}
                onChange={(e) =>
                  setBusinessHoursForm({ ...businessHoursForm, start_time: e.target.value })
                }
                disabled={!businessHoursForm.enabled}
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="end-time" className="text-xs text-muted-foreground">End</Label>
              <Input
                id="end-time"
                type="time"
                value={businessHoursForm.end_time}
                onChange={(e) =>
                  setBusinessHoursForm({ ...businessHoursForm, end_time: e.target.value })
                }
                disabled={!businessHoursForm.enabled}
                className="h-9"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="timezone" className="text-xs text-muted-foreground">Timezone</Label>
            <Select
              value={businessHoursForm.timezone}
              onValueChange={(value) =>
                setBusinessHoursForm({ ...businessHoursForm, timezone: value })
              }
              disabled={!businessHoursForm.enabled}
            >
              <SelectTrigger id="timezone" className="h-9">
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent>
                {timezones.map((tz) => (
                  <SelectItem key={tz} value={tz}>
                    {tz}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Within hours:</span>
              {settings.is_within_business_hours ? (
                <Badge variant="success" className="text-xs">Yes</Badge>
              ) : (
                <Badge variant="outline" className="text-xs">No</Badge>
              )}
            </div>
            <Button size="sm" variant="outline" onClick={handleBusinessHoursSubmit}>
              <Save className="h-3 w-3 mr-1.5" />
              Save
            </Button>
          </div>
        </div>

        {/* Queue Thresholds */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-medium">Queue Thresholds</h4>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="calls-waiting" className="text-xs text-muted-foreground">
                Max calls waiting before blocking outbound
              </Label>
              <Input
                id="calls-waiting"
                type="number"
                min="0"
                value={thresholdsForm.calls_waiting_threshold}
                onChange={(e) =>
                  setThresholdsForm({
                    ...thresholdsForm,
                    calls_waiting_threshold: parseInt(e.target.value) || 0,
                  })
                }
                className="h-9"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="oldest-wait" className="text-xs text-muted-foreground">
                Max wait time (seconds) before blocking
              </Label>
              <Input
                id="oldest-wait"
                type="number"
                min="0"
                value={thresholdsForm.holdtime_threshold_seconds}
                onChange={(e) =>
                  setThresholdsForm({
                    ...thresholdsForm,
                    holdtime_threshold_seconds: parseInt(e.target.value) || 0,
                  })
                }
                className="h-9"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="stable-polls" className="text-xs text-muted-foreground">
                Consecutive stable polls required
              </Label>
              <Input
                id="stable-polls"
                type="number"
                min="1"
                value={thresholdsForm.stable_polls_required}
                onChange={(e) =>
                  setThresholdsForm({
                    ...thresholdsForm,
                    stable_polls_required: parseInt(e.target.value) || 1,
                  })
                }
                className="h-9"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={handleThresholdsSubmit}>
              <Save className="h-3 w-3 mr-1.5" />
              Save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
