"use client";

import { useBackfillApi } from "@/hooks/useBackfillApi";
import type { BackfillSettings, BackfillSettingsUpdate } from "@/types/backfill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCallback, useEffect, useMemo, useState } from "react";

const CONTACT_DAYS: { key: string; label: string }[] = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
];

const TIMEZONE_OPTIONS = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "UTC",
];

function apiTimeToInput(value: string): string {
  return value.length >= 5 ? value.slice(0, 5) : value;
}

function inputTimeToApi(value: string): string {
  return value.length === 5 ? `${value}:00` : value;
}

function settingsToForm(s: BackfillSettings): BackfillSettingsUpdate {
  return {
    enabled: s.enabled,
    minimum_cancellation_notice_hours: s.minimum_cancellation_notice_hours,
    sms_batch_size_per_wave: s.sms_batch_size_per_wave,
    delay_between_waves_minutes: s.delay_between_waves_minutes,
    max_waves: s.max_waves,
    ai_call_escalation_enabled: s.ai_call_escalation_enabled,
    ai_call_quantity_per_wave: s.ai_call_quantity_per_wave,
    allowed_contact_days: s.allowed_contact_days,
    contact_window_start: s.contact_window_start,
    contact_window_end: s.contact_window_end,
    contact_window_timezone: s.contact_window_timezone,
    use_shared_holiday_calendar: s.use_shared_holiday_calendar,
    agent_blackout_dates: s.agent_blackout_dates,
    same_facility_required: s.same_facility_required,
    same_cpt_required: s.same_cpt_required,
    exclude_no_show_enabled: s.exclude_no_show_enabled,
    campaign_timeout_minutes: s.campaign_timeout_minutes,
    late_response_closeout_enabled: s.late_response_closeout_enabled,
    allowed_sms_template_id: s.allowed_sms_template_id,
    allowed_voice_template_id: s.allowed_voice_template_id,
    closeout_message_template_id: s.closeout_message_template_id,
  };
}

function formToPayload(form: BackfillSettingsUpdate): BackfillSettingsUpdate {
  return {
    ...form,
    contact_window_start: inputTimeToApi(apiTimeToInput(form.contact_window_start)),
    contact_window_end: inputTimeToApi(apiTimeToInput(form.contact_window_end)),
  };
}

function parseBlackoutText(text: string): string[] | null {
  const lines = text
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return lines.length > 0 ? lines : null;
}

function blackoutToText(dates: string[] | null): string {
  return dates?.join("\n") ?? "";
}

function NumberField({
  label,
  value,
  onChange,
  min = 1,
  id,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  id: string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        min={min}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function SettingsPanel() {
  const { getSettings, putSettings } = useBackfillApi();
  const [saved, setSaved] = useState<BackfillSettingsUpdate | null>(null);
  const [form, setForm] = useState<BackfillSettingsUpdate | null>(null);
  const [blackoutText, setBlackoutText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const data = await getSettings();
      const f = settingsToForm(data);
      setSaved(f);
      setForm(f);
      setBlackoutText(blackoutToText(data.agent_blackout_dates));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [getSettings]);

  useEffect(() => {
    load();
  }, [load]);

  const selectedDays = useMemo(() => {
    if (!form) return new Set<string>();
    return new Set(
      form.allowed_contact_days
        .split(",")
        .map((d) => d.trim().toLowerCase())
        .filter(Boolean)
    );
  }, [form]);

  const dirty = useMemo(() => {
    if (!saved || !form) return false;
    const withBlackout = {
      ...form,
      agent_blackout_dates: parseBlackoutText(blackoutText),
    };
    return JSON.stringify(withBlackout) !== JSON.stringify(saved);
  }, [saved, form, blackoutText]);

  const patch = (partial: Partial<BackfillSettingsUpdate>) => {
    setForm((prev) => (prev ? { ...prev, ...partial } : prev));
  };

  const toggleDay = (key: string) => {
    if (!form) return;
    const next = new Set(selectedDays);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    const order = CONTACT_DAYS.map((d) => d.key).filter((k) => next.has(k));
    patch({ allowed_contact_days: order.join(",") });
  };

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    setError("");
    try {
      const payload = formToPayload({
        ...form,
        agent_blackout_dates: parseBlackoutText(blackoutText),
      });
      const data = await putSettings(payload);
      const f = settingsToForm(data);
      setSaved(f);
      setForm(f);
      setBlackoutText(blackoutToText(data.agent_blackout_dates));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading settings...</p>;
  }

  if (!form) {
    return <p className="text-sm text-destructive">{error || "Settings unavailable."}</p>;
  }

  return (
    <div className="space-y-6">
      {dirty && (
        <div className="rounded-md border border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm">
          You have unsaved changes.
        </div>
      )}

      <p className="text-sm text-muted-foreground">
        Changes take effect on the next campaign created. Running campaigns keep the settings
        applied at creation time.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Agent</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="enabled">Agent enabled</Label>
            <CardDescription className="mt-1">
              When off, cancellations are recorded but no new campaigns are created.
            </CardDescription>
          </div>
          <Switch
            id="enabled"
            checked={form.enabled}
            onCheckedChange={(checked) => patch({ enabled: checked })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trigger settings</CardTitle>
        </CardHeader>
        <CardContent>
          <NumberField
            id="minimum_cancellation_notice_hours"
            label="Minimum cancellation notice (hours)"
            value={form.minimum_cancellation_notice_hours}
            onChange={(n) => patch({ minimum_cancellation_notice_hours: n })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Wave settings</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <NumberField
            id="sms_batch_size_per_wave"
            label="SMS batch size per wave"
            value={form.sms_batch_size_per_wave}
            onChange={(n) => patch({ sms_batch_size_per_wave: n })}
          />
          <NumberField
            id="delay_between_waves_minutes"
            label="Delay between waves (minutes)"
            value={form.delay_between_waves_minutes}
            min={0}
            onChange={(n) => patch({ delay_between_waves_minutes: n })}
          />
          <NumberField
            id="max_waves"
            label="Maximum waves"
            value={form.max_waves}
            onChange={(n) => patch({ max_waves: n })}
          />
          <NumberField
            id="ai_call_quantity_per_wave"
            label="AI calls per wave"
            value={form.ai_call_quantity_per_wave}
            onChange={(n) => patch({ ai_call_quantity_per_wave: n })}
          />
          <div className="sm:col-span-2 flex items-center justify-between gap-4">
            <Label htmlFor="ai_call_escalation_enabled">AI call escalation enabled</Label>
            <Switch
              id="ai_call_escalation_enabled"
              checked={form.ai_call_escalation_enabled}
              onCheckedChange={(checked) => patch({ ai_call_escalation_enabled: checked })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Hours of operation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Allowed contact days</Label>
            <div className="flex flex-wrap gap-2">
              {CONTACT_DAYS.map(({ key, label }) => (
                <Button
                  key={key}
                  type="button"
                  size="sm"
                  variant={selectedDays.has(key) ? "default" : "outline"}
                  onClick={() => toggleDay(key)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="contact_window_start">Contact window start</Label>
              <Input
                id="contact_window_start"
                type="time"
                value={apiTimeToInput(form.contact_window_start)}
                onChange={(e) =>
                  patch({ contact_window_start: inputTimeToApi(e.target.value) })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact_window_end">Contact window end</Label>
              <Input
                id="contact_window_end"
                type="time"
                value={apiTimeToInput(form.contact_window_end)}
                onChange={(e) => patch({ contact_window_end: inputTimeToApi(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact_window_timezone">Timezone</Label>
              <Select
                value={form.contact_window_timezone}
                onValueChange={(v) => patch({ contact_window_timezone: v })}
              >
                <SelectTrigger id="contact_window_timezone">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <SelectItem key={tz} value={tz}>
                      {tz}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Holiday suppression</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="use_shared_holiday_calendar">Use shared holiday calendar</Label>
            <Switch
              id="use_shared_holiday_calendar"
              checked={form.use_shared_holiday_calendar}
              onCheckedChange={(checked) => patch({ use_shared_holiday_calendar: checked })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="agent_blackout_dates">Agent-specific blackout dates</Label>
            <Textarea
              id="agent_blackout_dates"
              placeholder="YYYY-MM-DD, one per line (optional)"
              value={blackoutText}
              onChange={(e) => setBlackoutText(e.target.value)}
              rows={3}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Candidate matching rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4 opacity-70">
            <Label htmlFor="same_facility_required">Same facility required</Label>
            <Switch id="same_facility_required" checked disabled />
          </div>
          <div className="flex items-center justify-between gap-4 opacity-70">
            <Label htmlFor="same_cpt_required">Same CPT required</Label>
            <Switch id="same_cpt_required" checked disabled />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="exclude_no_show_enabled">Exclude no-show patients</Label>
            <Switch
              id="exclude_no_show_enabled"
              checked={form.exclude_no_show_enabled}
              onCheckedChange={(checked) => patch({ exclude_no_show_enabled: checked })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Campaign behavior</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="campaign_timeout_minutes">Campaign timeout (minutes)</Label>
            <Input
              id="campaign_timeout_minutes"
              type="number"
              min={1}
              placeholder="Optional"
              value={form.campaign_timeout_minutes ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                patch({
                  campaign_timeout_minutes: raw === "" ? null : Number(raw),
                });
              }}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="late_response_closeout_enabled">
              Late-response closeout message enabled
            </Label>
            <Switch
              id="late_response_closeout_enabled"
              checked={form.late_response_closeout_enabled}
              onCheckedChange={(checked) => patch({ late_response_closeout_enabled: checked })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Messaging templates</CardTitle>
          <CardDescription>Template library wiring arrives in Milestone 2.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-1">
          <div className="space-y-2">
            <Label>SMS template</Label>
            <Select value="none" disabled>
              <SelectTrigger>
                <SelectValue placeholder="Not configured (M2)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Not configured (M2)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Voice script template</Label>
            <Select value="none" disabled>
              <SelectTrigger>
                <SelectValue placeholder="Not configured (M2)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Not configured (M2)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Closeout message template</Label>
            <Select value="none" disabled>
              <SelectTrigger>
                <SelectValue placeholder="Not configured (M2)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Not configured (M2)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end pb-6">
        <Button type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  );
}
