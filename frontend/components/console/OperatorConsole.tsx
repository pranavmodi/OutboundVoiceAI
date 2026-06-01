"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
  PhoneCall,
  Monitor,
  Plus,
  Trash2,
  Radio,
  Users,
  Layers,
  CalendarDays,
  ChevronDown,
  MessageSquare,
  Bot,
  Play,
  Loader2,
  FileText,
  RotateCcw,
  KeyRound,
  Eye,
  EyeOff,
} from "lucide-react";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { useApi } from "@/hooks/useApi";
import type { ApiKeysStatusResponse } from "@/types";
import type {
  SystemSettings,
  BusinessHours,
  HolidayEntry,
  QueueThresholds,
  DispatcherSettings,
  SimulationScenario,
} from "@/types";

const OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"];
const GEMINI_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Perseus", "Zephyr"];
const GROK_VOICES = ["eve", "ara", "rex", "sal", "leo"];

function VoiceRow({
  label,
  provider,
  voices,
  currentVoice,
  onVoiceChange,
  onPreview,
}: {
  label: string;
  provider: string;
  voices: string[];
  currentVoice: string;
  onVoiceChange: (voice: string) => void;
  onPreview: (provider: string, voice: string) => Promise<string | null>;
}) {
  const [previewing, setPreviewing] = useState<string | null>(null);

  const handlePreview = async (voice: string) => {
    setPreviewing(voice);
    try {
      const url = await onPreview(provider, voice);
      if (url) {
        const audio = new Audio(url);
        audio.play();
        audio.onended = () => {
          setPreviewing(null);
          URL.revokeObjectURL(url);
        };
      } else {
        setPreviewing(null);
      }
    } catch {
      setPreviewing(null);
    }
  };

  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex items-center gap-2">
        <Select value={currentVoice} onValueChange={onVoiceChange}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {voices.map((v) => (
              <SelectItem key={v} value={v}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handlePreview(currentVoice)}
          disabled={previewing !== null}
          className="h-9 px-3"
        >
          {previewing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          <span className="ml-1.5">Preview</span>
        </Button>
      </div>
    </div>
  );
}

function OpenAIVadCard({
  silenceMs,
  prefixMs,
  threshold,
  onSave,
}: {
  silenceMs: number;
  prefixMs: number;
  threshold: number;
  onSave: (silenceMs: number, prefixMs: number, threshold: number) => Promise<void>;
}) {
  // Local form state — only commit on Save so users can experiment without
  // half-applied values mid-typing.
  const [silence, setSilence] = useState(silenceMs);
  const [prefix, setPrefix] = useState(prefixMs);
  const [thresh, setThresh] = useState(threshold);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  // Reflect external settings changes (other tab saved, settings reloaded).
  useEffect(() => { setSilence(silenceMs); }, [silenceMs]);
  useEffect(() => { setPrefix(prefixMs); }, [prefixMs]);
  useEffect(() => { setThresh(threshold); }, [threshold]);

  const dirty = silence !== silenceMs || prefix !== prefixMs || thresh !== threshold;

  const handleSave = async () => {
    setErrorText(null);
    if (silence < 100 || silence > 2000) {
      setErrorText("Silence must be between 100 and 2000 ms.");
      return;
    }
    if (prefix < 0 || prefix > 1000) {
      setErrorText("Prefix must be between 0 and 1000 ms.");
      return;
    }
    if (thresh < 0 || thresh > 1) {
      setErrorText("Threshold must be between 0.0 and 1.0.");
      return;
    }
    setSaving(true);
    setSaved(false);
    try {
      await onSave(silence, prefix, thresh);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setErrorText(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSilence(700);
    setPrefix(300);
    setThresh(0.85);
  };

  return (
    <div className="space-y-3 mt-3 rounded-md border p-3">
      <div className="flex items-center gap-2">
        <Label className="text-sm font-medium">OpenAI Realtime — Turn detection</Label>
        <InfoTooltip content="Server-VAD knobs the OpenAI Realtime API uses to decide when the patient finished speaking. Lower silence_ms cuts dead air; lower threshold is more sensitive to quiet speakers. Applies on the next call." />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor="vad-silence" className="text-xs">Silence (ms)</Label>
            <InfoTooltip content="How long the AI waits in silence after the patient stops talking before it responds. Lower = snappier replies but more likely to cut off mid-sentence pauses, especially with elderly or slow speakers." />
          </div>
          <Input
            id="vad-silence"
            type="number"
            min={100}
            max={2000}
            step={50}
            value={silence}
            onChange={(e) => setSilence(parseInt(e.target.value || "0", 10))}
          />
          <p className="text-[11px] text-muted-foreground">100–2000. Default 700.</p>
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor="vad-prefix" className="text-xs">Prefix (ms)</Label>
            <InfoTooltip content="How much audio just before detected speech is kept on the patient's turn, so the first syllable isn't clipped. Doesn't change response latency — only what the model hears of the utterance." />
          </div>
          <Input
            id="vad-prefix"
            type="number"
            min={0}
            max={1000}
            step={50}
            value={prefix}
            onChange={(e) => setPrefix(parseInt(e.target.value || "0", 10))}
          />
          <p className="text-[11px] text-muted-foreground">0–1000. Default 300.</p>
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor="vad-threshold" className="text-xs">Threshold</Label>
            <InfoTooltip content="How loud audio must be to count as speech (0 = anything, 1 = only very loud). Lower picks up quiet or elderly speakers; higher rejects background noise and breathing." />
          </div>
          <Input
            id="vad-threshold"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={thresh}
            onChange={(e) => setThresh(parseFloat(e.target.value || "0"))}
          />
          <p className="text-[11px] text-muted-foreground">0.0–1.0. Default 0.85.</p>
        </div>
      </div>
      {errorText && (
        <p className="text-xs text-destructive">{errorText}</p>
      )}
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
          Save VAD
        </Button>
        <Button variant="outline" size="sm" onClick={handleReset} disabled={saving}>
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
          Reset to defaults
        </Button>
        {saved && (
          <span className="text-xs text-emerald-600 flex items-center gap-1">
            <CheckCircle className="h-3.5 w-3.5" />
            Saved
          </span>
        )}
      </div>
    </div>
  );
}


function VoiceSelector({
  openaiVoice,
  geminiVoice,
  grokVoice,
  onSave,
  onPreview,
}: {
  openaiVoice: string;
  geminiVoice: string;
  grokVoice: string;
  onSave: (openaiVoice: string, geminiVoice: string, grokVoice: string) => Promise<void>;
  onPreview: (provider: string, voice: string) => Promise<string | null>;
}) {
  return (
    <div className="space-y-3 mt-3">
      <VoiceRow
        label="OpenAI Voice"
        provider="openai"
        voices={OPENAI_VOICES}
        currentVoice={openaiVoice}
        onVoiceChange={(v) => onSave(v, geminiVoice, grokVoice)}
        onPreview={onPreview}
      />
      <VoiceRow
        label="Gemini Voice"
        provider="gemini"
        voices={GEMINI_VOICES}
        currentVoice={geminiVoice}
        onVoiceChange={(v) => onSave(openaiVoice, v, grokVoice)}
        onPreview={onPreview}
      />
      <VoiceRow
        label="xAI Grok Voice"
        provider="grok"
        voices={GROK_VOICES}
        currentVoice={grokVoice}
        onVoiceChange={(v) => onSave(openaiVoice, geminiVoice, v)}
        onPreview={onPreview}
      />
    </div>
  );
}

function ApiKeyRow({
  label,
  provider,
  status,
  onSaved,
}: {
  label: string;
  provider: "openai" | "gemini" | "grok";
  status: { configured: boolean; source: "db" | "env" | "none"; preview: string } | undefined;
  onSaved: () => Promise<void>;
}) {
  const { updateApiKey, clearApiKey, revealApiKey } = useApi();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [showValue, setShowValue] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [revealing, setRevealing] = useState(false);

  // Hide a revealed key whenever the underlying status changes (saved/cleared).
  useEffect(() => {
    setRevealedKey(null);
  }, [status?.preview, status?.configured, status?.source]);

  const startEdit = async () => {
    setErrorMessage(null);
    setRevealedKey(null);
    setShowValue(false);
    setEditing(true);
    if (status?.configured) {
      const existing = await revealApiKey(provider);
      setValue(existing ?? "");
    } else {
      setValue("");
    }
  };

  const handleReveal = async () => {
    if (revealedKey !== null) {
      setRevealedKey(null);
      return;
    }
    setRevealing(true);
    try {
      const plaintext = await revealApiKey(provider);
      if (plaintext !== null) {
        setRevealedKey(plaintext);
      }
    } finally {
      setRevealing(false);
    }
  };

  const cancelEdit = () => {
    setEditing(false);
    setValue("");
    setErrorMessage(null);
  };

  const save = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setErrorMessage("Key cannot be empty");
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      await updateApiKey(provider, trimmed);
      await onSaved();
      setEditing(false);
      setValue("");
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!confirm(`Clear the ${label} key from the database? The OS environment variable (if set) will be used as fallback.`)) {
      return;
    }
    setSaving(true);
    try {
      await clearApiKey(provider);
      await onSaved();
    } finally {
      setSaving(false);
    }
  };

  const badgeForSource = () => {
    if (!status?.configured) {
      return <Badge variant="outline" className="text-red-600 border-red-600">Not configured</Badge>;
    }
    if (status.source === "env") {
      return <Badge variant="outline" className="text-amber-600 border-amber-600">From env var</Badge>;
    }
    return <Badge variant="outline" className="text-emerald-600 border-emerald-600">Saved</Badge>;
  };

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Label className="text-sm font-medium">{label}</Label>
          {badgeForSource()}
        </div>
        {status?.configured && !editing && (
          <span className="text-xs font-mono text-muted-foreground break-all max-w-[60%] text-right">
            {revealedKey ?? status.preview}
          </span>
        )}
      </div>

      {!editing ? (
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={startEdit}>
            {status?.configured ? "Replace" : "Add key"}
          </Button>
          {status?.configured && (
            <Button size="sm" variant="ghost" onClick={handleReveal} disabled={revealing}>
              {revealing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              ) : revealedKey !== null ? (
                <EyeOff className="h-3.5 w-3.5 mr-1" />
              ) : (
                <Eye className="h-3.5 w-3.5 mr-1" />
              )}
              {revealedKey !== null ? "Hide" : "View"}
            </Button>
          )}
          {status?.configured && status.source === "db" && (
            <Button size="sm" variant="ghost" onClick={handleClear} disabled={saving}>
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              Clear
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Input
              type={showValue ? "text" : "password"}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={provider === "openai" ? "sk-..." : "AIza..."}
              className="font-mono text-xs"
              autoFocus
            />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowValue((v) => !v)}
              type="button"
              className="h-9 px-2"
            >
              {showValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
          </div>
          {errorMessage && (
            <p className="text-xs text-red-600">{errorMessage}</p>
          )}
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Validate &amp; save
            </Button>
            <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={saving}>
              Cancel
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Saving makes a test call to {provider === "openai" ? "OpenAI" : "Gemini"} to confirm the key works. New calls use the updated key without a restart.
          </p>
        </div>
      )}
    </div>
  );
}

function ApiKeysCard() {
  const { getApiKeysStatus } = useApi();
  const [status, setStatus] = useState<ApiKeysStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    const s = await getApiKeysStatus();
    setStatus(s);
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-medium">Provider API Keys</h4>
        <InfoTooltip content="Configure the API keys used to reach OpenAI and Gemini. Updates apply on the next call without restarting the server. Keys are stored in the database; clearing one falls back to the OS environment variable if set." />
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : (
        <div className="space-y-3">
          <ApiKeyRow label="OpenAI" provider="openai" status={status?.openai} onSaved={refresh} />
          <ApiKeyRow label="Google Gemini" provider="gemini" status={status?.gemini} onSaved={refresh} />
          <ApiKeyRow label="xAI Grok" provider="grok" status={status?.grok} onSaved={refresh} />
        </div>
      )}
    </div>
  );
}

interface OperatorConsoleProps {
  settings: SystemSettings | null;
  timezones: string[];
  callMode: string;
  scenarios: SimulationScenario[];
  onCallModeChange: (mode: string) => void;
  onVoiceProviderChange: (provider: string) => void;
  onSetSystemEnabled: (enabled: boolean) => Promise<void>;
  onUpdateBusinessHours: (businessHours: BusinessHours) => Promise<void>;
  onUpdateQueueThresholds: (thresholds: QueueThresholds) => Promise<void>;
  onUpdateDispatcherSettings: (dispatcherSettings: DispatcherSettings) => Promise<void>;
  onSetMockMode: (enabled: boolean, mockPhone: string) => Promise<void>;
  onUpdateDailyReport: (config: { enabled: boolean; webhook_url: string; hour: number; timezone: string }) => Promise<void>;
  onSendTestDailyReport: () => Promise<{ sent: boolean } | null>;
  onSetQueueSource: (source: string) => Promise<void>;
  onSetPatientSource: (source: string) => Promise<void>;
  onSetActiveScenario: (id: string) => Promise<void>;
  onUpdateVoices: (openaiVoice: string, geminiVoice: string, grokVoice: string) => Promise<void>;
  onUpdateOpenAIVad: (silenceMs: number, prefixMs: number, threshold: number) => Promise<void>;
  onPreviewVoice: (provider: string, voice: string) => Promise<string | null>;
  onUpdateCallGreeting: (greeting: string) => Promise<void>;
}

export function OperatorConsole({
  settings,
  timezones,
  callMode,
  scenarios,
  onCallModeChange,
  onVoiceProviderChange,
  onSetSystemEnabled,
  onUpdateBusinessHours,
  onUpdateQueueThresholds,
  onUpdateDispatcherSettings,
  onSetMockMode,
  onUpdateDailyReport,
  onSendTestDailyReport,
  onSetQueueSource,
  onSetPatientSource,
  onSetActiveScenario,
  onUpdateVoices,
  onUpdateOpenAIVad,
  onPreviewVoice,
  onUpdateCallGreeting,
}: OperatorConsoleProps) {
  const [businessHoursForm, setBusinessHoursForm] = useState<BusinessHours>({
    start_time: "08:00",
    end_time: "17:00",
    enabled: false,
    timezone: "America/New_York",
    days_of_week: [0, 1, 2, 3, 4],  // Mon-Fri
    holidays: [],
  });

  const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const [thresholdsForm, setThresholdsForm] = useState<QueueThresholds>({
    calls_waiting_threshold: 1,
    holdtime_threshold_seconds: 30,
    stable_polls_required: 3,
  });

  const [dispatcherForm, setDispatcherForm] = useState<DispatcherSettings>({
    poll_interval: 10,
    dispatch_timeout: 30,
    max_attempts_ordered: 4,
    max_attempts_other: 4,
    min_hours_between: 6,
    max_parallel_calls: 1,
    dispatch_pacing_seconds: 1,
  });

  const DEFAULT_GREETING = "Hi, this is Ashley with Precise Imaging. We received your doctor's imaging order and need to schedule your appointment. Are you available now to schedule your appointment?";
  const [greetingText, setGreetingText] = useState(settings?.dispatcher_settings?.call_greeting || DEFAULT_GREETING);
  const [greetingSaving, setGreetingSaving] = useState(false);
  const [greetingSaved, setGreetingSaved] = useState(false);

  const [mockPhoneInput, setMockPhoneInput] = useState(settings?.mock_phone || "");
  const [holidayEditorOpen, setHolidayEditorOpen] = useState(false);
  const [dailyReportForm, setDailyReportForm] = useState({
    enabled: settings?.daily_report?.enabled ?? false,
    webhook_url: settings?.daily_report?.webhook_url ?? "",
    hour: settings?.daily_report?.hour ?? 7,
    timezone: settings?.daily_report?.timezone ?? "America/Los_Angeles",
  });
  const [dailyReportSaving, setDailyReportSaving] = useState(false);
  const [dailyReportTestStatus, setDailyReportTestStatus] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setBusinessHoursForm(settings.business_hours);
      setThresholdsForm(settings.queue_thresholds);
      setDispatcherForm(settings.dispatcher_settings);
      setMockPhoneInput(settings.mock_phone || "");
      setGreetingText(settings.dispatcher_settings?.call_greeting || DEFAULT_GREETING);
      if (settings.daily_report) {
        setDailyReportForm({
          enabled: settings.daily_report.enabled,
          webhook_url: settings.daily_report.webhook_url,
          hour: settings.daily_report.hour,
          timezone: settings.daily_report.timezone,
        });
      }
    }
  }, [settings]);

  const handleBusinessHoursSubmit = async () => {
    await onUpdateBusinessHours(businessHoursForm);
  };

  const handleDailyReportSave = async () => {
    setDailyReportSaving(true);
    setDailyReportTestStatus(null);
    try {
      await onUpdateDailyReport(dailyReportForm);
    } finally {
      setDailyReportSaving(false);
    }
  };

  const handleDailyReportTest = async () => {
    setDailyReportTestStatus("Sending...");
    try {
      const result = await onSendTestDailyReport();
      setDailyReportTestStatus(
        result?.sent ? "Test report sent successfully" : "Failed to send (check webhook URL and logs)"
      );
    } catch {
      setDailyReportTestStatus("Failed to send test report");
    }
    setTimeout(() => setDailyReportTestStatus(null), 6000);
  };

  const handleAddHoliday = () => {
    const next: HolidayEntry = {
      date: "",
      name: "",
      recurring: true,
    };
    setBusinessHoursForm({
      ...businessHoursForm,
      holidays: [...(businessHoursForm.holidays || []), next],
    });
    setHolidayEditorOpen(true);
  };

  const handleUpdateHoliday = (index: number, patch: Partial<HolidayEntry>) => {
    const holidays = [...(businessHoursForm.holidays || [])];
    holidays[index] = { ...holidays[index], ...patch };
    setBusinessHoursForm({ ...businessHoursForm, holidays });
  };

  const handleRemoveHoliday = (index: number) => {
    const holidays = [...(businessHoursForm.holidays || [])];
    holidays.splice(index, 1);
    setBusinessHoursForm({ ...businessHoursForm, holidays });
  };

  const handleBusinessHoursEnabledChange = async (enabled: boolean) => {
    const newForm = { ...businessHoursForm, enabled };
    setBusinessHoursForm(newForm);
    await onUpdateBusinessHours(newForm);
  };

  const handleThresholdsSubmit = async () => {
    await onUpdateQueueThresholds(thresholdsForm);
  };

  const handleDispatcherSubmit = async () => {
    await onUpdateDispatcherSettings(dispatcherForm);
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
            <p className="text-sm font-medium flex items-center gap-1.5">
              System Status
              <InfoTooltip content="Master switch for the outbound calling system. When disabled, the dispatcher will not place any calls regardless of other settings." />
            </p>
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
          <InfoTooltip content="Web mode simulates calls in your browser — you speak as the patient using your microphone. Twilio mode places real phone calls to actual phone numbers." />
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
            ? "Audio streams between your browser and the voice AI. You speak as the patient through your microphone."
            : "Twilio dials the patient's phone number. Audio streams between the phone line and the voice AI. The browser still shows transcripts and controls."}
        </p>
      </div>

      <Separator />

      <ApiKeysCard />

      <Separator />

      {/* Voice Provider */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Voice AI Provider</h4>
          <InfoTooltip content="Choose which AI model powers the voice conversations. OpenAI uses GPT Realtime API. Gemini uses Google's Live API — typically faster and more natural sounding. xAI uses Grok Voice Agent API." />
        </div>
        <div className="flex items-center gap-4">
          <Select value={settings?.voice_provider || "openai"} onValueChange={onVoiceProviderChange}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">
                <span className="flex items-center gap-2">
                  OpenAI Realtime
                </span>
              </SelectItem>
              <SelectItem value="gemini">
                <span className="flex items-center gap-2">
                  Google Gemini Live
                </span>
              </SelectItem>
              <SelectItem value="grok">
                <span className="flex items-center gap-2">
                  xAI Grok Voice
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          {(() => {
            const provider = settings?.voice_provider || "openai";
            const label = provider === "gemini" ? "Gemini" : provider === "grok" ? "Grok" : "OpenAI";
            const color =
              provider === "gemini" ? "text-blue-600 border-blue-600"
              : provider === "grok" ? "text-purple-600 border-purple-600"
              : "text-emerald-600 border-emerald-600";
            return <Badge variant="outline" className={color}>{label}</Badge>;
          })()}
        </div>
        <VoiceSelector
          openaiVoice={settings?.dispatcher_settings?.openai_voice || "alloy"}
          geminiVoice={settings?.dispatcher_settings?.gemini_voice || "Aoede"}
          grokVoice={settings?.dispatcher_settings?.grok_voice || "eve"}
          onSave={onUpdateVoices}
          onPreview={onPreviewVoice}
        />
        <OpenAIVadCard
          silenceMs={settings?.dispatcher_settings?.openai_vad_silence_ms ?? 700}
          prefixMs={settings?.dispatcher_settings?.openai_vad_prefix_ms ?? 300}
          threshold={settings?.dispatcher_settings?.openai_vad_threshold ?? 0.85}
          onSave={onUpdateOpenAIVad}
        />
      </div>

      <Separator />

      {/* Call Script / Greeting Editor */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Call Script</h4>
          <InfoTooltip content="The opening greeting Ashley speaks when a patient answers. This is what the AI says at the start of every call. Changes take effect on the next call." />
        </div>
        <p className="text-xs text-muted-foreground">
          Edit the initial greeting the AI speaks when a patient answers. The patient's first name is inserted automatically.
        </p>
        <Textarea
          value={greetingText}
          onChange={(e) => {
            setGreetingText(e.target.value);
            setGreetingSaved(false);
          }}
          rows={4}
          className="text-sm font-mono"
          placeholder="Hi, this is Ashley with Precise Imaging..."
        />
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={async () => {
              setGreetingSaving(true);
              setGreetingSaved(false);
              try {
                await onUpdateCallGreeting(greetingText);
                setGreetingSaved(true);
                setTimeout(() => setGreetingSaved(false), 3000);
              } finally {
                setGreetingSaving(false);
              }
            }}
            disabled={greetingSaving}
          >
            {greetingSaving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <Save className="h-3.5 w-3.5 mr-1.5" />
            )}
            Save Greeting
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const defaultGreeting =
                "Hi, this is Ashley with Precise Imaging. We received your doctor's imaging order and need to schedule your appointment. Are you available now to schedule your appointment?";
              setGreetingText(defaultGreeting);
              setGreetingSaved(false);
            }}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            Reset to Default
          </Button>
          {greetingSaved && (
            <span className="text-xs text-emerald-600 flex items-center gap-1">
              <CheckCircle className="h-3.5 w-3.5" />
              Saved
            </span>
          )}
        </div>
      </div>

      <Separator />

      {/* Queue Source */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Queue Source</h4>
          <InfoTooltip content="Determines where queue metrics (calls waiting, agents available) come from. Simulation uses mock data you control. Live connects to FreePBX/Asterisk for real call center status." />
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
          <InfoTooltip content="Determines where the outbound call list comes from. Simulation uses mock patient data from scenarios. Live connects to RadFlow/EHR for real patients needing callbacks." />
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

      {/* Active Scenario Selector - only visible when either source is simulation */}
      {(settings.queue_source === "simulation" || settings.patient_source === "simulation") && (
        <>
          <Separator />

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              <h4 className="text-sm font-medium">Active Scenario</h4>
              <InfoTooltip content="Selects which simulation scenario is loaded. Changing scenarios resets the patient queue, call logs, and dispatcher state. Use the Simulation tab to edit scenario details." />
            </div>
            <p className="text-xs text-muted-foreground">
              Select which simulation scenario to use. Changing the active scenario will reset mock queue/patient data, clear call logs, and restart the dispatcher.
            </p>
            <div className="flex items-center gap-4">
              <Select
                value={settings.active_scenario_id || ""}
                onValueChange={onSetActiveScenario}
              >
                <SelectTrigger className="w-64">
                  <SelectValue placeholder="Select scenario..." />
                </SelectTrigger>
                <SelectContent>
                  {scenarios.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      <span className="flex items-center gap-2">
                        {s.label}
                        {s.is_builtin && (
                          <Badge variant="outline" className="text-xs">Builtin</Badge>
                        )}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </>
      )}

      <Separator />

      {/* Mock Mode */}
      <div className="space-y-4 rounded-lg border border-orange-200 bg-orange-50/50 dark:border-orange-900 dark:bg-orange-950/20 p-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-orange-600 dark:text-orange-400" />
          <h4 className="text-sm font-medium">Test Mode</h4>
          <InfoTooltip content="Route all Twilio calls and SMS to a test number instead of real patients." />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="mock-mode" className="text-sm flex items-center gap-1.5">
                Mock Mode
                <InfoTooltip content="When enabled, all Twilio calls and SMS are redirected to the mock phone number below instead of the patient's real number. Useful for end-to-end testing without calling patients." />
              </Label>
              <p className="text-xs text-muted-foreground">
                Redirect all outbound calls and SMS to a test number
              </p>
            </div>
            <Switch
              id="mock-mode"
              checked={settings.mock_mode}
              onCheckedChange={(checked) => onSetMockMode(checked, settings.mock_phone)}
            />
          </div>
          {settings.mock_mode && (
            <div className="space-y-1">
              <Label htmlFor="mock-phone" className="text-xs text-muted-foreground flex items-center gap-1.5">
                Mock Phone Number
                <InfoTooltip content="All Twilio calls and SMS will be sent to this number instead of the patient's real number. Use E.164 format (+1...)." />
              </Label>
              <Input
                id="mock-phone"
                placeholder="+15551234567"
                value={mockPhoneInput}
                onChange={(e) => setMockPhoneInput(e.target.value)}
                onBlur={() => { if (mockPhoneInput !== settings.mock_phone) onSetMockMode(settings.mock_mode, mockPhoneInput); }}
                onKeyDown={(e) => { if (e.key === "Enter" && mockPhoneInput !== settings.mock_phone) onSetMockMode(settings.mock_mode, mockPhoneInput); }}
                className="h-9"
              />
            </div>
          )}
        </div>

      </div>

      <Separator />

      {/* Daily Slack Report */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Daily Slack Report</h4>
          <InfoTooltip content="Once per day at the configured hour, posts yesterday's call summary (calls placed, transfers, voicemails, etc.) to a Slack webhook." />
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="daily-report-enabled" className="text-sm flex items-center gap-1.5">
              Enable daily report
            </Label>
            <p className="text-xs text-muted-foreground">
              Post yesterday's stats to Slack every day
            </p>
          </div>
          <Switch
            id="daily-report-enabled"
            checked={dailyReportForm.enabled}
            onCheckedChange={(checked) => setDailyReportForm({ ...dailyReportForm, enabled: checked })}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="daily-report-webhook" className="text-xs text-muted-foreground">
              Slack Webhook URL
            </Label>
            <Input
              id="daily-report-webhook"
              type="text"
              placeholder="https://hooks.slack.com/services/..."
              value={dailyReportForm.webhook_url}
              onChange={(e) => setDailyReportForm({ ...dailyReportForm, webhook_url: e.target.value })}
              className="h-9 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="daily-report-hour" className="text-xs text-muted-foreground">
              Send at (hour, 0-23)
            </Label>
            <Input
              id="daily-report-hour"
              type="number"
              min={0}
              max={23}
              value={dailyReportForm.hour}
              onChange={(e) => {
                const h = parseInt(e.target.value, 10);
                setDailyReportForm({ ...dailyReportForm, hour: isNaN(h) ? 0 : Math.max(0, Math.min(23, h)) });
              }}
              className="h-9"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="daily-report-tz" className="text-xs text-muted-foreground">
              Timezone
            </Label>
            <Select
              value={dailyReportForm.timezone}
              onValueChange={(v) => setDailyReportForm({ ...dailyReportForm, timezone: v })}
            >
              <SelectTrigger id="daily-report-tz" className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {timezones.map((tz) => (
                  <SelectItem key={tz} value={tz}>{tz}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" onClick={handleDailyReportSave} disabled={dailyReportSaving}>
            <Save className="h-3 w-3 mr-1.5" />
            {dailyReportSaving ? "Saving..." : "Save"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleDailyReportTest}
            disabled={!dailyReportForm.webhook_url}
            title="Send yesterday's summary to Slack now (ignores the enable toggle)"
          >
            Send Test Now
          </Button>
          {dailyReportTestStatus && (
            <span className="text-xs text-muted-foreground">{dailyReportTestStatus}</span>
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
            <InfoTooltip content="Restricts outbound calls to specific hours and days. Prevents AI from calling patients outside business hours or on weekends." />
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="business-hours-enabled" className="text-sm flex items-center gap-1.5">
              Enforce hours
              <InfoTooltip content="When enabled, calls are only allowed during the specified time window and days. When disabled, calls can be placed 24/7." />
            </Label>
            <Switch
              id="business-hours-enabled"
              checked={businessHoursForm.enabled}
              onCheckedChange={handleBusinessHoursEnabledChange}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="start-time" className="text-xs text-muted-foreground flex items-center gap-1">
                Start
                <InfoTooltip content="Earliest time calls can begin. Uses 24-hour format in the selected timezone." />
              </Label>
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
              <Label htmlFor="end-time" className="text-xs text-muted-foreground flex items-center gap-1">
                End
                <InfoTooltip content="Latest time calls can be placed. Calls in progress may continue past this time." />
              </Label>
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
            <Label htmlFor="timezone" className="text-xs text-muted-foreground flex items-center gap-1">
              Timezone
              <InfoTooltip content="All business hours are evaluated in this timezone. Make sure it matches your call center's operating timezone." />
            </Label>
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

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground flex items-center gap-1">
              Days of Week
              <InfoTooltip content="Select which days outbound calls are allowed. Typically Mon-Fri to avoid weekend calls. Click to toggle each day." />
            </Label>
            <div className="flex flex-wrap gap-1">
              {DAY_LABELS.map((day, idx) => {
                const isSelected = businessHoursForm.days_of_week?.includes(idx) ?? false;
                return (
                  <button
                    key={day}
                    type="button"
                    disabled={!businessHoursForm.enabled}
                    onClick={() => {
                      const current = businessHoursForm.days_of_week ?? [];
                      const newDays = isSelected
                        ? current.filter((d) => d !== idx)
                        : [...current, idx].sort((a, b) => a - b);
                      setBusinessHoursForm({ ...businessHoursForm, days_of_week: newDays });
                    }}
                    className={`px-2 py-1 text-xs rounded border transition-colors ${
                      isSelected
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background text-muted-foreground border-border hover:bg-muted"
                    } ${!businessHoursForm.enabled ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2 rounded-lg border p-3">
            <button
              type="button"
              onClick={() => setHolidayEditorOpen((v) => !v)}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-muted-foreground" />
                <p className="text-sm font-medium flex items-center gap-1.5">
                  Holiday Calendar
                  <InfoTooltip content="Calls are blocked on matching holiday dates even when business hours/day rules are otherwise valid." />
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">
                  {(businessHoursForm.holidays || []).length} holiday{(businessHoursForm.holidays || []).length !== 1 ? "s" : ""}
                </Badge>
                <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${holidayEditorOpen ? "rotate-180" : ""}`} />
              </div>
            </button>

            {holidayEditorOpen && (
              <div className="space-y-3 pt-2">
                {(businessHoursForm.holidays || []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No holidays configured. Add entries to block outbound calls on those dates.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {(businessHoursForm.holidays || []).map((holiday, idx) => (
                      <div key={idx} className="grid grid-cols-12 gap-2 items-center rounded border p-2">
                        <Input
                          type="date"
                          value={holiday.date}
                          onChange={(e) => handleUpdateHoliday(idx, { date: e.target.value })}
                          className="col-span-4 h-8"
                        />
                        <Input
                          placeholder="Holiday name"
                          value={holiday.name}
                          onChange={(e) => handleUpdateHoliday(idx, { name: e.target.value })}
                          className="col-span-5 h-8"
                        />
                        <div className="col-span-2 flex items-center justify-end gap-2">
                          <Label className="text-[11px] text-muted-foreground">Yearly</Label>
                          <Switch
                            checked={holiday.recurring}
                            onCheckedChange={(checked) => handleUpdateHoliday(idx, { recurring: checked })}
                          />
                        </div>
                        <div className="col-span-1 flex justify-end">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleRemoveHoliday(idx)}
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Button type="button" size="sm" variant="outline" onClick={handleAddHoliday}>
                  <Plus className="h-3.5 w-3.5 mr-1.5" />
                  Add Holiday
                </Button>
                <Button type="button" size="sm" onClick={handleBusinessHoursSubmit}>
                  <Save className="h-3.5 w-3.5 mr-1.5" />
                  Save Holidays
                </Button>
              </div>
            )}
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
            <InfoTooltip content="Gating conditions that must be met before placing outbound calls. Prevents AI calls when the call center is already overwhelmed with inbound calls." />
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="calls-waiting" className="text-xs text-muted-foreground flex items-center gap-1">
                Max calls waiting before blocking outbound
                <InfoTooltip content="If more than this many calls are waiting in the inbound queue, outbound calls are paused. Set to 0 to disable this check." />
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
              <Label htmlFor="oldest-wait" className="text-xs text-muted-foreground flex items-center gap-1">
                Max wait time (seconds) before blocking
                <InfoTooltip content="If any caller has been waiting longer than this, outbound calls are paused. Ensures agents handle long-waiting inbound callers first." />
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
              <Label htmlFor="stable-polls" className="text-xs text-muted-foreground flex items-center gap-1">
                Consecutive stable polls required
                <InfoTooltip content="How many consecutive queue checks must pass thresholds before outbound is allowed. Prevents calls during brief lulls in a busy period." />
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

      <Separator />

      {/* Dispatcher Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">Dispatcher Settings</h4>
          <InfoTooltip content="Controls how the dispatcher selects and places outbound calls. These settings affect call frequency and retry behavior." />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="poll-interval" className="text-xs text-muted-foreground flex items-center gap-1">
              Poll interval (seconds)
              <InfoTooltip content="How often the dispatcher checks queue status and attempts to place calls. Lower values = more frequent checks." />
            </Label>
            <Input
              id="poll-interval"
              type="number"
              min="1"
              value={dispatcherForm.poll_interval}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  poll_interval: parseInt(e.target.value) || 1,
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="dispatch-timeout" className="text-xs text-muted-foreground flex items-center gap-1">
              Dispatch timeout (seconds)
              <InfoTooltip content="How long to wait for the frontend to acknowledge a dispatch request before timing out and trying again." />
            </Label>
            <Input
              id="dispatch-timeout"
              type="number"
              min="1"
              value={dispatcherForm.dispatch_timeout}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  dispatch_timeout: parseInt(e.target.value) || 1,
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="max-attempts-ordered" className="text-xs text-muted-foreground flex items-center gap-1">
              Max attempts — Ordered status
              <InfoTooltip content="Max combined (AI + human) attempts before an Ordered-status patient is moved to Couldnt Schedule and HL7 is sent to RadFlow." />
            </Label>
            <Input
              id="max-attempts-ordered"
              type="number"
              min="1"
              value={dispatcherForm.max_attempts_ordered}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  max_attempts_ordered: parseInt(e.target.value) || 1,
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="max-attempts-other" className="text-xs text-muted-foreground flex items-center gap-1">
              Max attempts — No Show / Needs to Reschedule
              <InfoTooltip content="Max combined (AI + human) attempts for No Show and Needs to Reschedule patients before they flip to Couldnt Schedule." />
            </Label>
            <Input
              id="max-attempts-other"
              type="number"
              min="1"
              value={dispatcherForm.max_attempts_other}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  max_attempts_other: parseInt(e.target.value) || 1,
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="min-hours-between" className="text-xs text-muted-foreground flex items-center gap-1">
              Min hours between attempts
              <InfoTooltip content="Minimum wait time before retrying a patient who didn't answer or requested a callback. Prevents calling the same person repeatedly in a short time." />
            </Label>
            <Input
              id="min-hours-between"
              type="number"
              min="0"
              value={dispatcherForm.min_hours_between}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  min_hours_between: parseInt(e.target.value) || 0,
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="max-parallel-calls" className="text-xs text-muted-foreground flex items-center gap-1">
              Parallel calls
              <InfoTooltip content="How many outbound calls run at the same time. 1 = sequential (one call ends before the next starts). Voicemails are counted as 'done' the moment AMD detects the beep, so the next call can start while the AI finishes leaving the message. Capped at 10." />
            </Label>
            <Input
              id="max-parallel-calls"
              type="number"
              min="1"
              max="10"
              value={dispatcherForm.max_parallel_calls ?? 1}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  max_parallel_calls: Math.max(1, Math.min(10, parseInt(e.target.value) || 1)),
                })
              }
              className="h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="dispatch-pacing" className="text-xs text-muted-foreground flex items-center gap-1">
              Dispatch pacing (s)
              <InfoTooltip content="Minimum gap between successive call starts. Prevents bursting past Twilio's per-second rate limits when running parallel calls. 1s is enough for typical accounts." />
            </Label>
            <Input
              id="dispatch-pacing"
              type="number"
              min="0"
              value={dispatcherForm.dispatch_pacing_seconds ?? 1}
              onChange={(e) =>
                setDispatcherForm({
                  ...dispatcherForm,
                  dispatch_pacing_seconds: Math.max(0, parseInt(e.target.value) || 0),
                })
              }
              className="h-9"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={handleDispatcherSubmit}>
            <Save className="h-3 w-3 mr-1.5" />
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
