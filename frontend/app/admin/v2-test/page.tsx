"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  CircleSlash,
  FlaskConical,
  Info,
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

import { useV2Test } from "@/hooks/useV2Test";
import type {
  FlagOverrides,
  GateEvaluateResponse,
  Modality,
  OutstandingTaskSpec,
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


function V2TestPageInner() {
  const { listScenarios, evaluateGate } = useV2Test();

  const [catalog, setCatalog] = useState<Scenario[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(BLANK_FORM);
  const [gate, setGate] = useState<GateEvaluateResponse | null>(null);
  const [gateLoading, setGateLoading] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);

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

          {/* Center: call controls (placeholder until Phase B) */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">Mock call</CardTitle>
              <CardDescription>
                Runs the scenario through the v2 voice flow with a synthetic
                patient. Browser audio only — no Twilio originate.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border border-dashed p-6 flex flex-col items-center justify-center text-center gap-2 min-h-[200px]">
                <CircleSlash className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm font-medium">Mock calling not yet wired</p>
                <p className="text-xs text-muted-foreground max-w-xs">
                  The <code className="font-mono">POST /api/v2-test/start-call</code>{" "}
                  endpoint lands in Phase B. The gate-decision panel on the right
                  is live now — that&apos;s the part you can validate today.
                </p>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="block w-full">
                    <Button className="w-full" disabled>
                      Start mock call
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>Phase B — coming next.</TooltipContent>
              </Tooltip>

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

          {/* Right: gate decision */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">Gate decision</CardTitle>
              <CardDescription>
                Live evaluation against the same{" "}
                <code className="font-mono">IntakeV2Gate</code> used by{" "}
                <code className="font-mono">CallOrchestrator</code>.
                Overlay forces master on, allowlist=[&quot;TEST&quot;], canary=100.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <GatePanel
                loading={gateLoading}
                error={gateError}
                decision={gate}
              />
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
