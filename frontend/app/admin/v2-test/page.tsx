"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  CircleSlash,
  FlaskConical,
  Info,
  Loader2,
  Phone,
  PhoneOff,
  RefreshCw,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { useAudio } from "@/hooks/useAudio";
import { useV2Test } from "@/hooks/useV2Test";
import { useVoiceWS } from "@/hooks/useWebSocket";
import type {
  FlagOverrides,
  GateEvaluateResponse,
  Modality,
  OutstandingTaskSpec,
  RecentRunSummary,
  Scenario,
} from "@/types/v2-test";


const ENABLED = process.env.NEXT_PUBLIC_ENABLE_V2_TEST_PAGE === "true";

const DEFAULT_FLAGS: FlagOverrides = {
  mode_voice_capture: true,
  mode_portal_copilot: false,
  multi_call_resume: false,
};

// Human-readable explanations for gate reason codes. Keep in sync with
// app/services/intake_v2_gate.py.
const REASON_COPY: Record<string, string> = {
  eligible: "Admitted — this scenario would take the v2 path.",
  master_off: "Skipped — master_enabled is off in the overlay.",
  no_order_id: "Skipped — scenario has no order_id.",
  tenant_not_allowed: "Skipped — tenant is not in the allowlist.",
  outside_canary: "Skipped — order's canary bucket is outside the configured percentage.",
};


interface FormState {
  scenarioId: string;
  patientName: string;
  tenantId: string;
  orderId: string;
  dobOnOrder: string;
  patientDob: string;
  modality: Modality;
  outstandingTasks: OutstandingTaskSpec[];
  flags: FlagOverrides;
}

const BLANK_FORM: FormState = {
  scenarioId: "",
  patientName: "",
  tenantId: "TEST",
  orderId: "",
  dobOnOrder: "",
  patientDob: "",
  modality: "MR_CONTRAST",
  outstandingTasks: [],
  flags: DEFAULT_FLAGS,
};

function formFromScenario(s: Scenario): FormState {
  return {
    scenarioId: s.id,
    patientName: s.patient.name,
    tenantId: s.patient.tenant_id,
    orderId: s.patient.order_id,
    dobOnOrder: s.patient.dob_on_order,
    patientDob: s.expected_patient_dob,
    modality: s.modality,
    outstandingTasks: s.outstanding_tasks,
    flags: s.flag_overrides,
  };
}


export default function V2TestPage() {
  if (!ENABLED) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Not enabled</CardTitle>
            <CardDescription>
              The /v2-test page is gated by{" "}
              <code className="font-mono text-xs">NEXT_PUBLIC_ENABLE_V2_TEST_PAGE</code>.
              Set it to <code className="font-mono text-xs">true</code> at build time to enable.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return <V2TestPageInner />;
}


type CallPhase = "idle" | "starting" | "active" | "ending" | "ended";

function V2TestPageInner() {
  const { listScenarios, evaluateGate, startCall, endCall, listRecentRuns } = useV2Test();
  const voice = useVoiceWS();
  const audio = useAudio();

  const [catalog, setCatalog] = useState<Scenario[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(BLANK_FORM);
  const [gate, setGate] = useState<GateEvaluateResponse | null>(null);
  const [gateLoading, setGateLoading] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);

  const [phase, setPhase] = useState<CallPhase>("idle");
  const [activeCallId, setActiveCallId] = useState<string | null>(null);
  const [callError, setCallError] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRunSummary[]>([]);
  const [recentRunsLoading, setRecentRunsLoading] = useState(false);

  // Mirror live refs so the audio-callback closure (set once) can reach
  // the latest voice/audio handles without re-wiring on every render.
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  const audioRef = useRef(audio);
  audioRef.current = audio;
  // Mirror activeCallId + endCall into refs so the once-only unmount
  // cleanup can read the latest values without re-binding on every render.
  const activeCallIdRef = useRef<string | null>(null);
  activeCallIdRef.current = activeCallId;
  const endCallRef = useRef(endCall);
  endCallRef.current = endCall;

  // Load catalog on mount.
  useEffect(() => {
    let alive = true;
    listScenarios()
      .then((scenarios) => {
        if (alive) {
          setCatalog(scenarios);
          setCatalogError(null);
        }
      })
      .catch((e: unknown) => {
        if (alive) {
          setCatalogError(e instanceof Error ? e.message : "Failed to load scenarios");
        }
      });
    return () => {
      alive = false;
    };
  }, [listScenarios]);

  // Debounced gate-evaluate on any form change that affects the gate decision.
  // The gate depends on order_id, tenant_id, and the canary/master flags —
  // not on patient name or DOB, but we re-fetch on any change for simplicity.
  useEffect(() => {
    const handle = setTimeout(async () => {
      setGateLoading(true);
      setGateError(null);
      try {
        const decision = await evaluateGate({
          order_id: form.orderId || null,
          tenant_id: form.tenantId || null,
          overlay: {
            master_enabled: true,
            tenant_allowlist: ["TEST"],
            order_canary_pct: 100,
          },
        });
        setGate(decision);
      } catch (e) {
        setGateError(e instanceof Error ? e.message : "Failed to evaluate gate");
        setGate(null);
      } finally {
        setGateLoading(false);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [evaluateGate, form.orderId, form.tenantId]);

  const handleLoadScenario = useCallback(
    (id: string) => {
      const found = catalog.find((s) => s.id === id);
      if (found) {
        setForm(formFromScenario(found));
      }
    },
    [catalog]
  );

  const handleReset = useCallback(() => {
    if (form.scenarioId) {
      handleLoadScenario(form.scenarioId);
    } else {
      setForm(BLANK_FORM);
    }
  }, [form.scenarioId, handleLoadScenario]);

  const dobMatches = useMemo(
    () => form.dobOnOrder.trim() !== "" && form.dobOnOrder === form.patientDob,
    [form.dobOnOrder, form.patientDob]
  );

  // -- Recent runs ---------------------------------------------------------

  const refreshRecentRuns = useCallback(async () => {
    setRecentRunsLoading(true);
    try {
      const runs = await listRecentRuns(20);
      setRecentRuns(runs);
    } catch (e) {
      console.warn("recent-runs fetch failed", e);
    } finally {
      setRecentRunsLoading(false);
    }
  }, [listRecentRuns]);

  useEffect(() => {
    refreshRecentRuns();
  }, [refreshRecentRuns]);

  // -- Voice + audio plumbing ---------------------------------------------

  // Wire WS audio out → speakers and mic in → WS — once. Subsequent renders
  // hit the refs, so we don't reattach on every state change (which would
  // also reset the once-only callback chain in the hooks).
  const audioWiredRef = useRef(false);
  useEffect(() => {
    if (audioWiredRef.current) return;
    audioWiredRef.current = true;
    voice.onAudioReceived((data) => {
      audioRef.current.playAudio(data);
    });
    audio.onAudioData((data) => {
      voiceRef.current.sendAudio(data);
    });
  }, [voice, audio]);

  // React to call lifecycle events from the WS so the UI matches reality
  // even when the backend ends the call autonomously (timeout, error, etc.).
  useEffect(() => {
    if (voice.isCallActive && phase === "starting") {
      setPhase("active");
    }
    if (!voice.isCallActive && (phase === "active" || phase === "ending")) {
      setPhase("ended");
      audioRef.current.stopRecording();
      // Refresh the runs list once the call_log row is finalized.
      void refreshRecentRuns();
    }
  }, [voice.isCallActive, phase, refreshRecentRuns]);

  // Tear down WS + mic on unmount so a navigation-away during an active
  // call doesn't strand the orchestrator (callbacks would still be
  // attached to a dead WS and the call would have no audio sink).
  useEffect(() => {
    return () => {
      // If a call is still active when the page unmounts (navigation
      // away, tab close, hot reload mid-call, etc.), fire-and-forget the
      // end-call endpoint so the orchestrator's call_log row gets cleaned
      // up server-side. Without this, the row stays at outcome=
      // 'in_progress' forever and the startup sweep is the only thing
      // that eventually disconnects it.
      const callId = activeCallIdRef.current;
      if (callId) {
        endCallRef.current(callId).catch(() => {
          // best-effort — backend may already be tearing down via the
          // WebSocket close; either way we just want the side effect.
        });
      }
      try {
        audioRef.current.stopRecording();
      } catch {
        // noop
      }
      voiceRef.current.disconnect();
    };
  }, []);

  // -- Start / end handlers -----------------------------------------------

  const formToScenario = useCallback((): Scenario => {
    const baseId = form.scenarioId || `adhoc-${Date.now()}`;
    return {
      id: baseId,
      name: form.patientName || baseId,
      description: "",
      patient: {
        name: form.patientName || "Synthetic Test",
        tenant_id: form.tenantId || "TEST",
        order_id: form.orderId,
        dob_on_order: form.dobOnOrder,
      },
      expected_patient_dob: form.patientDob,
      modality: form.modality,
      outstanding_tasks: form.outstandingTasks,
      flag_overrides: form.flags,
    };
  }, [form]);

  const handleStartCall = useCallback(async () => {
    if (phase === "starting" || phase === "active" || phase === "ending") return;
    setCallError(null);
    setPhase("starting");

    try {
      // 1. Open WS so callbacks are attached BEFORE the orchestrator starts.
      //    The page is the only WS client; we never send a `start_call`
      //    message — the POST below drives the orchestrator directly.
      if (!voice.connected) {
        voice.connect();
        for (let i = 0; i < 30; i++) {
          await new Promise((r) => setTimeout(r, 100));
          if (voiceRef.current.connected) break;
        }
      }
      if (!voiceRef.current.connected) {
        throw new Error("Voice WebSocket did not connect within 3s");
      }

      // 2. Start mic recording (web mode only — there's no Twilio path here).
      await audio.startRecording();
      // Small settle so the AudioContext is fully running before we hand
      // it to the orchestrator's first audio frame.
      await new Promise((r) => setTimeout(r, 150));

      // 3. Drive the orchestrator from the server side. The WS callbacks
      //    we already attached will fire on call_started / transcript /
      //    audio normally.
      const resp = await startCall(formToScenario());
      setActiveCallId(resp.call_id);
      // Phase will transition to "active" via the voice.isCallActive
      // effect once the orchestrator fires on_call_started.
    } catch (e) {
      setCallError(e instanceof Error ? e.message : "Failed to start mock call");
      setPhase("idle");
      try {
        audioRef.current.stopRecording();
      } catch {
        // noop
      }
    }
  }, [phase, voice, audio, startCall, formToScenario]);

  const handleEndCall = useCallback(async () => {
    if (!activeCallId || phase === "idle" || phase === "ended") return;
    setPhase("ending");
    try {
      await endCall(activeCallId);
      // Phase transitions to "ended" via the voice.isCallActive effect.
    } catch (e) {
      setCallError(e instanceof Error ? e.message : "Failed to end mock call");
      setPhase("active"); // back to active — let user try again
    }
  }, [activeCallId, phase, endCall]);

  const handleResetCallUi = useCallback(() => {
    setPhase("idle");
    setActiveCallId(null);
    setCallError(null);
  }, []);

  const callBusy = phase === "starting" || phase === "active" || phase === "ending";

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur-lg">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/admin"
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              Admin
            </Link>
            <Separator orientation="vertical" className="h-6" />
            <div className="flex items-center gap-2">
              <FlaskConical className="h-5 w-5 text-primary" />
              <span className="font-semibold">V2 Intake — Test Lane</span>
              <Badge variant="secondary" className="text-xs">internal</Badge>
            </div>
          </div>
          <span className="text-xs text-muted-foreground">
            Synthetic patients only — no real calls dialed.
          </span>
        </div>
      </header>

      <main className="container mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: scenario picker + editor */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">Scenario</CardTitle>
              <CardDescription>
                Pick a starter scenario or edit fields freely. Forms a synthetic
                patient — never touches production data.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="scenario-select">Built-in scenarios</Label>
                <Select
                  value={form.scenarioId}
                  onValueChange={(v) => handleLoadScenario(v)}
                >
                  <SelectTrigger id="scenario-select">
                    <SelectValue placeholder="Choose a starter scenario…" />
                  </SelectTrigger>
                  <SelectContent>
                    {catalog.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {catalogError && (
                  <p className="text-xs text-destructive">{catalogError}</p>
                )}
                {form.scenarioId && (
                  <p className="text-xs text-muted-foreground">
                    {catalog.find((s) => s.id === form.scenarioId)?.description}
                  </p>
                )}
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2 space-y-1.5">
                  <Label htmlFor="patient-name">Patient name</Label>
                  <Input
                    id="patient-name"
                    value={form.patientName}
                    onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="tenant-id">Tenant ID</Label>
                  <Input
                    id="tenant-id"
                    value={form.tenantId}
                    onChange={(e) => setForm((f) => ({ ...f, tenantId: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="order-id">Order ID</Label>
                  <Input
                    id="order-id"
                    value={form.orderId}
                    onChange={(e) => setForm((f) => ({ ...f, orderId: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="dob-on-order">DOB on order</Label>
                  <Input
                    id="dob-on-order"
                    type="date"
                    value={form.dobOnOrder}
                    onChange={(e) => setForm((f) => ({ ...f, dobOnOrder: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="patient-dob" className="flex items-center gap-1">
                    DOB patient states
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-3 w-3 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>
                        What the test patient will say on the call. Differs from
                        DOB on order to exercise the identity-mismatch path.
                      </TooltipContent>
                    </Tooltip>
                  </Label>
                  <Input
                    id="patient-dob"
                    type="date"
                    value={form.patientDob}
                    onChange={(e) => setForm((f) => ({ ...f, patientDob: e.target.value }))}
                  />
                </div>
                <div className="col-span-2 space-y-1.5">
                  <Label htmlFor="modality">Modality</Label>
                  <Select
                    value={form.modality}
                    onValueChange={(v) => setForm((f) => ({ ...f, modality: v as Modality }))}
                  >
                    <SelectTrigger id="modality">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="RADIATION">Radiation</SelectItem>
                      <SelectItem value="MR_NON_CONTRAST">MR — no contrast</SelectItem>
                      <SelectItem value="MR_CONTRAST">MR — with contrast</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Flag overrides</Label>
                <div className="space-y-2">
                  <FlagRow
                    label="mode_voice_capture"
                    description="Capture intake fields by voice on the call."
                    value={form.flags.mode_voice_capture}
                    onChange={(v) =>
                      setForm((f) => ({ ...f, flags: { ...f.flags, mode_voice_capture: v } }))
                    }
                  />
                  <FlagRow
                    label="mode_portal_copilot"
                    description="Offer the SMS portal as an alternative to voice."
                    value={form.flags.mode_portal_copilot}
                    onChange={(v) =>
                      setForm((f) => ({ ...f, flags: { ...f.flags, mode_portal_copilot: v } }))
                    }
                  />
                  <FlagRow
                    label="multi_call_resume"
                    description="Resume captured fields across multiple calls."
                    value={form.flags.multi_call_resume}
                    onChange={(v) =>
                      setForm((f) => ({ ...f, flags: { ...f.flags, multi_call_resume: v } }))
                    }
                  />
                </div>
              </div>

              <Separator />

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Outstanding intake tasks</Label>
                  <Badge variant="outline">{form.outstandingTasks.length}</Badge>
                </div>
                {form.outstandingTasks.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No tasks — agent should hand off immediately with{" "}
                    <code className="font-mono">NO_INTAKE_NEEDED</code>.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {form.outstandingTasks.map((t, i) => (
                      <li
                        key={`${t.category}-${t.field_id}-${i}`}
                        className="flex items-center justify-between text-sm rounded-md border px-2.5 py-1.5"
                      >
                        <span className="font-mono text-xs">{t.field_id}</span>
                        <Badge variant="secondary" className="text-xs">
                          {t.category}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={handleReset}
                disabled={!form.scenarioId}
              >
                <RefreshCw className="h-3.5 w-3.5 mr-2" />
                Reset to loaded scenario
              </Button>
            </CardContent>
          </Card>

          {/* Center: call controls */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">Mock call</CardTitle>
              <CardDescription>
                Runs the scenario with a synthetic patient. Browser audio only —
                no Twilio originate, no production data touched.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <CallStatusPanel
                phase={phase}
                callError={callError}
                voiceStatus={voice.callStatus}
                voiceError={voice.error}
                audioLevel={audio.audioLevel}
                isRecording={audio.isRecording}
                activeCallId={activeCallId}
              />

              {phase === "idle" || phase === "ended" ? (
                <Button
                  className="w-full"
                  onClick={handleStartCall}
                  disabled={
                    !form.orderId || !form.dobOnOrder || !form.patientDob ||
                    gate?.eligible === false
                  }
                >
                  <Phone className="h-4 w-4 mr-2" />
                  Start mock call
                </Button>
              ) : (
                <Button
                  className="w-full"
                  variant="destructive"
                  onClick={handleEndCall}
                  disabled={phase === "ending" || phase === "starting"}
                >
                  {phase === "ending" ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <PhoneOff className="h-4 w-4 mr-2" />
                  )}
                  End call
                </Button>
              )}

              {phase === "ended" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={handleResetCallUi}
                >
                  Clear and re-arm
                </Button>
              )}

              {gate && gate.eligible === false && (phase === "idle" || phase === "ended") && (
                <p className="text-xs text-muted-foreground">
                  Gate would skip this scenario (
                  <code className="font-mono">{gate.reason}</code>) — fix it
                  before starting a call.
                </p>
              )}

              {!dobMatches && form.dobOnOrder && form.patientDob && (
                <div className="text-xs rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-amber-700 dark:text-amber-300">
                  <span className="font-medium">Identity will fail.</span>{" "}
                  DOB on order ({form.dobOnOrder}) doesn&apos;t match what the
                  patient will state ({form.patientDob}). Expected handoff:{" "}
                  <code className="font-mono">IDENTITY_VERIFICATION_FAILED</code>.
                </div>
              )}
            </CardContent>
          </Card>

          {/* Right: gate decision when idle, live transcript during call */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">
                {callBusy || phase === "ended" ? "Live transcript" : "Gate decision"}
              </CardTitle>
              <CardDescription>
                {callBusy || phase === "ended" ? (
                  <>Streaming from <code className="font-mono">/ws/voice</code>. Only complete utterances are shown.</>
                ) : (
                  <>
                    Live evaluation against the same{" "}
                    <code className="font-mono">IntakeV2Gate</code> used by{" "}
                    <code className="font-mono">CallOrchestrator</code>.
                    Overlay forces master on, allowlist=[&quot;TEST&quot;], canary=100.
                  </>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {callBusy || phase === "ended" ? (
                <TranscriptPanel transcript={voice.transcript} />
              ) : (
                <GatePanel
                  loading={gateLoading}
                  error={gateError}
                  decision={gate}
                />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Recent test runs */}
        <div className="mt-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="text-base">Recent test runs</CardTitle>
                <CardDescription>
                  Last 20 /v2-test calls. Filtered to{" "}
                  <code className="font-mono">mock_mode=true</code> AND{" "}
                  <code className="font-mono">TEST-PAT-*</code> so production
                  history stays clean.
                </CardDescription>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={refreshRecentRuns}
                disabled={recentRunsLoading}
              >
                {recentRunsLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
              </Button>
            </CardHeader>
            <CardContent>
              <RecentRunsPanel runs={recentRuns} loading={recentRunsLoading} />
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}


function FlagRow({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border px-2.5 py-2">
      <div className="flex-1 min-w-0">
        <p className="font-mono text-xs">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  );
}


function GatePanel({
  loading,
  error,
  decision,
}: {
  loading: boolean;
  error: string | null;
  decision: GateEvaluateResponse | null;
}) {
  if (error) {
    return (
      <div className="text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!decision || loading) {
    return (
      <div className="text-sm text-muted-foreground">
        {loading ? "Evaluating…" : "Edit the form to evaluate the gate."}
      </div>
    );
  }

  const eligibleColor = decision.eligible
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-muted-foreground";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {decision.eligible ? (
          <CheckCircle2 className={`h-5 w-5 ${eligibleColor}`} />
        ) : (
          <CircleSlash className={`h-5 w-5 ${eligibleColor}`} />
        )}
        <span className={`font-semibold ${eligibleColor}`}>
          {decision.eligible ? "Eligible" : "Skipped"}
        </span>
        <Badge variant="outline" className="font-mono text-xs">
          {decision.reason}
        </Badge>
      </div>

      <p className="text-sm text-muted-foreground">
        {REASON_COPY[decision.reason] ?? "Unknown reason code."}
      </p>

      <Separator />

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Canary bucket</p>
          <p className="font-mono">
            {decision.canary_bucket === null ? "—" : `${decision.canary_bucket} / 99`}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Admitted at</p>
          <p className="font-mono">
            {decision.canary_bucket === null
              ? "—"
              : `canary_pct ≥ ${decision.canary_bucket + 1}`}
          </p>
        </div>
      </div>
    </div>
  );
}


function CallStatusPanel({
  phase,
  callError,
  voiceStatus,
  voiceError,
  audioLevel,
  isRecording,
  activeCallId,
}: {
  phase: CallPhase;
  callError: string | null;
  voiceStatus: string | null;
  voiceError: string | null;
  audioLevel: number;
  isRecording: boolean;
  activeCallId: string | null;
}) {
  const label = (
    phase === "idle" ? "Ready" :
    phase === "starting" ? "Connecting…" :
    phase === "active" ? "Live" :
    phase === "ending" ? "Hanging up…" :
    "Ended"
  );

  const dotColor =
    phase === "active" ? "bg-emerald-500" :
    phase === "starting" || phase === "ending" ? "bg-amber-500" :
    phase === "ended" ? "bg-muted-foreground" :
    "bg-muted";

  // Audio level is 0..1 from the mic analyser; clamp for the meter width.
  const levelPct = Math.min(100, Math.round(audioLevel * 100));

  return (
    <div className="rounded-md border p-4 space-y-3 min-h-[200px]">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotColor} ${phase === "active" ? "animate-pulse" : ""}`} />
        <span className="font-medium text-sm">{label}</span>
        {activeCallId && (
          <Badge variant="outline" className="font-mono text-[10px] ml-auto">
            {activeCallId.slice(0, 8)}…
          </Badge>
        )}
      </div>

      {(phase === "active" || phase === "starting") && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">
            Mic {isRecording ? "(recording)" : "(idle)"}
          </p>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-[width] duration-100"
              style={{ width: `${levelPct}%` }}
            />
          </div>
        </div>
      )}

      {voiceStatus && (
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">status:</span> {voiceStatus}
        </p>
      )}

      {(callError || voiceError) && (
        <div className="text-xs rounded-md border border-destructive/40 bg-destructive/5 px-2.5 py-2 text-destructive">
          {callError || voiceError}
        </div>
      )}

      {phase === "idle" && (
        <p className="text-xs text-muted-foreground">
          Click <strong>Start mock call</strong> to dial the synthetic patient.
          Browser will request mic access.
        </p>
      )}
    </div>
  );
}


function TranscriptPanel({
  transcript,
}: {
  transcript: Array<{ speaker: string; text: string }>;
}) {
  if (transcript.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        Waiting for the first utterance…
      </div>
    );
  }
  return (
    <ScrollArea className="h-[320px] pr-3">
      <ul className="space-y-2.5">
        {transcript.map((entry, i) => (
          <li
            key={i}
            className={`rounded-md px-3 py-2 text-sm ${
              entry.speaker === "ai"
                ? "bg-muted/50"
                : "bg-emerald-500/5 border border-emerald-500/20"
            }`}
          >
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-0.5">
              {entry.speaker === "ai" ? "Agent" : entry.speaker === "patient" ? "Tester" : entry.speaker}
            </div>
            <div className="whitespace-pre-wrap">{entry.text}</div>
          </li>
        ))}
      </ul>
    </ScrollArea>
  );
}


function RecentRunsPanel({
  runs,
  loading,
}: {
  runs: RecentRunSummary[];
  loading: boolean;
}) {
  if (loading && runs.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4 flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-2">
        No test runs yet. Start one above.
      </p>
    );
  }
  return (
    <div className="rounded-md border divide-y">
      {runs.map((r) => (
        <div
          key={r.call_id}
          className="px-3 py-2.5 flex items-center justify-between gap-3 text-sm"
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium truncate">{r.patient_name}</span>
              <Badge variant="outline" className="font-mono text-[10px]">
                {r.order_id || "—"}
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground">
              {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
              {r.duration_seconds > 0 && (
                <> · {r.duration_seconds}s</>
              )}
            </div>
          </div>
          <Badge variant="secondary" className="font-mono text-[10px]">
            {r.outcome || "in_progress"}
          </Badge>
        </div>
      ))}
    </div>
  );
}
