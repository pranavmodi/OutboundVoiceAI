"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Phone,
  Users,
  Settings,
  Plus,
  Trash2,
  RotateCcw,
} from "lucide-react";

// ---------- Types ----------

interface QueueRow {
  queue_name: string;
  calls_waiting: number;
  oldest_wait_seconds: number;
  agents_available: number;
  agents_logged_in: number;
}

interface PatientRow {
  name: string;
  phone: string;
  language: string;
  has_abandoned_before: boolean;
  has_called_in_before: boolean;
  ai_called_before: boolean;
  attempt_count: number;
}

interface DispatcherSettings {
  poll_interval: number;
  dispatch_timeout: number;
  max_attempts: number;
  min_hours_between: number;
}

interface SimulationConfig {
  queue: {
    ami_connected: boolean;
    queues: QueueRow[];
  };
  patients: PatientRow[];
  dispatcher: DispatcherSettings;
}

interface Scenario {
  id: string;
  label: string;
  description: string;
  amiConnected: boolean;
  queues: QueueRow[];
  patients: PatientRow[];
  dispatcher: DispatcherSettings;
}

// ---------- Scenarios ----------

const SCENARIOS: Scenario[] = [
  {
    id: "default",
    label: "Default (Full Queue)",
    description: "3 queues with agents available, 7 patients across all priority buckets. Standard dispatcher settings.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 2, agents_logged_in: 3 },
      { queue_name: "scheduling_es", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 },
      { queue_name: "intake", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 2 },
    ],
    patients: [
      { name: "John Smith", phone: "555-0101", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Maria Garcia", phone: "555-0102", language: "es", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Robert Johnson", phone: "555-0103", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: true, attempt_count: 1 },
      { name: "Emily Davis", phone: "555-0104", language: "en", has_abandoned_before: false, has_called_in_before: true, ai_called_before: false, attempt_count: 0 },
      { name: "Michael Wilson", phone: "555-0105", language: "en", has_abandoned_before: false, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Sarah Brown", phone: "555-0106", language: "en", has_abandoned_before: false, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Wei Zhang", phone: "555-0107", language: "zh", has_abandoned_before: false, has_called_in_before: true, ai_called_before: false, attempt_count: 0 },
    ],
    dispatcher: { poll_interval: 10, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
  {
    id: "single_patient_ready",
    label: "Single Patient Ready",
    description: "One patient waiting, one agent available. Simplest scenario to trigger a single outbound call immediately.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 },
    ],
    patients: [
      { name: "Alice Taylor", phone: "555-0201", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
    ],
    dispatcher: { poll_interval: 5, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
  {
    id: "busy_queues",
    label: "Busy Queues (Blocked)",
    description: "All queues are overloaded with calls waiting and no agents free. Outbound should be blocked by gating conditions.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 5, oldest_wait_seconds: 120, agents_available: 0, agents_logged_in: 3 },
      { queue_name: "scheduling_es", calls_waiting: 3, oldest_wait_seconds: 90, agents_available: 0, agents_logged_in: 1 },
      { queue_name: "intake", calls_waiting: 4, oldest_wait_seconds: 60, agents_available: 0, agents_logged_in: 2 },
    ],
    patients: [
      { name: "John Smith", phone: "555-0101", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Maria Garcia", phone: "555-0102", language: "es", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
    ],
    dispatcher: { poll_interval: 10, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
  {
    id: "ami_down",
    label: "AMI Disconnected",
    description: "AMI connection is down. Dispatcher will block all outbound calls regardless of queue or patient state.",
    amiConnected: false,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 2, agents_logged_in: 3 },
    ],
    patients: [
      { name: "John Smith", phone: "555-0101", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
    ],
    dispatcher: { poll_interval: 10, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
  {
    id: "multilingual",
    label: "Multilingual Patients",
    description: "Three patients in different languages (EN, ES, ZH), one agent available. Tests language routing.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 },
      { queue_name: "scheduling_es", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 },
    ],
    patients: [
      { name: "John Smith", phone: "555-0101", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Maria Garcia", phone: "555-0102", language: "es", has_abandoned_before: true, has_called_in_before: false, ai_called_before: false, attempt_count: 0 },
      { name: "Wei Zhang", phone: "555-0107", language: "zh", has_abandoned_before: false, has_called_in_before: true, ai_called_before: false, attempt_count: 0 },
    ],
    dispatcher: { poll_interval: 10, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
  {
    id: "retry_scenario",
    label: "Retry Exhaustion",
    description: "Two patients near their max attempt limit. One has 2/3 attempts used, the other has 3/3 (exhausted). Only the first should be eligible.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 },
    ],
    patients: [
      { name: "Robert Johnson", phone: "555-0103", language: "en", has_abandoned_before: true, has_called_in_before: false, ai_called_before: true, attempt_count: 2 },
      { name: "Emily Davis", phone: "555-0104", language: "en", has_abandoned_before: false, has_called_in_before: true, ai_called_before: true, attempt_count: 3 },
    ],
    dispatcher: { poll_interval: 5, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 0 },
  },
  {
    id: "empty_queue",
    label: "No Patients",
    description: "Agents available but no patients in the outbound queue. Dispatcher should tick but find no candidate.",
    amiConnected: true,
    queues: [
      { queue_name: "scheduling_en", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 2, agents_logged_in: 3 },
    ],
    patients: [],
    dispatcher: { poll_interval: 5, dispatch_timeout: 30, max_attempts: 3, min_hours_between: 6 },
  },
];

// ---------- Props ----------

interface SimulationConsoleProps {
  onApplySimulation: (config: SimulationConfig) => Promise<void>;
}

// ---------- Component ----------

export function SimulationConsole({ onApplySimulation }: SimulationConsoleProps) {
  const defaultScenario = SCENARIOS[0];
  const [selectedScenarioId, setSelectedScenarioId] = useState(defaultScenario.id);
  const [queues, setQueues] = useState<QueueRow[]>(() => defaultScenario.queues.map(q => ({ ...q })));
  const [amiConnected, setAmiConnected] = useState(defaultScenario.amiConnected);
  const [patients, setPatients] = useState<PatientRow[]>(() => defaultScenario.patients.map(p => ({ ...p })));
  const [dispatcher, setDispatcher] = useState<DispatcherSettings>({ ...defaultScenario.dispatcher });
  const [applying, setApplying] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Scenario loader
  const loadScenario = (scenarioId: string) => {
    const scenario = SCENARIOS.find(s => s.id === scenarioId);
    if (!scenario) return;
    setSelectedScenarioId(scenarioId);
    setQueues(scenario.queues.map(q => ({ ...q })));
    setAmiConnected(scenario.amiConnected);
    setPatients(scenario.patients.map(p => ({ ...p })));
    setDispatcher({ ...scenario.dispatcher });
    setFeedback(null);
  };

  // Queue handlers
  const updateQueue = (index: number, field: keyof QueueRow, value: string | number) => {
    setQueues(prev => prev.map((q, i) => i === index ? { ...q, [field]: value } : q));
  };

  const addQueue = () => {
    setQueues(prev => [...prev, { queue_name: "", calls_waiting: 0, oldest_wait_seconds: 0, agents_available: 1, agents_logged_in: 1 }]);
  };

  const removeQueue = (index: number) => {
    setQueues(prev => prev.filter((_, i) => i !== index));
  };

  // Patient handlers
  const updatePatient = (index: number, field: keyof PatientRow, value: string | number | boolean) => {
    setPatients(prev => prev.map((p, i) => i === index ? { ...p, [field]: value } : p));
  };

  const addPatient = () => {
    setPatients(prev => [...prev, { name: "", phone: "", language: "en", has_abandoned_before: false, has_called_in_before: false, ai_called_before: false, attempt_count: 0 }]);
  };

  const removePatient = (index: number) => {
    setPatients(prev => prev.filter((_, i) => i !== index));
  };

  // Dispatcher handlers
  const updateDispatcher = (field: keyof DispatcherSettings, value: number) => {
    setDispatcher(prev => ({ ...prev, [field]: value }));
  };

  // Apply
  const handleApply = async () => {
    setApplying(true);
    setFeedback(null);
    try {
      await onApplySimulation({
        queue: { ami_connected: amiConnected, queues },
        patients,
        dispatcher,
      });
      setFeedback({ type: "success", message: "Simulation applied and dispatcher restarted." });
    } catch {
      setFeedback({ type: "error", message: "Failed to apply simulation configuration." });
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Feedback */}
      {feedback && (
        <div className={`rounded-md p-4 ${feedback.type === "success" ? "bg-green-500/10 text-green-700 dark:text-green-400" : "bg-destructive/10 text-destructive"}`}>
          {feedback.message}
        </div>
      )}

      {/* Scenario Preset Selector */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5" />
            Scenario Preset
          </CardTitle>
          <CardDescription>
            Load a pre-built scenario to quickly configure all sections below. You can still edit individual values after loading.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Select value={selectedScenarioId} onValueChange={loadScenario}>
            <SelectTrigger className="w-full sm:w-80">
              <SelectValue placeholder="Select a scenario..." />
            </SelectTrigger>
            <SelectContent>
              {SCENARIOS.map(s => (
                <SelectItem key={s.id} value={s.id}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-sm text-muted-foreground">
            {SCENARIOS.find(s => s.id === selectedScenarioId)?.description}
          </p>
        </CardContent>
      </Card>

      {/* Section 1: Queue Configuration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Phone className="h-5 w-5" />
                Queue Configuration
              </CardTitle>
              <CardDescription>
                Simulates FreePBX/Asterisk call queues. The dispatcher checks these metrics each tick to decide whether outbound calls are safe to make. When calls are waiting or agents are unavailable, outbound is blocked.
              </CardDescription>
            </div>
            <Badge variant="secondary">{queues.length} queues</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* AMI Toggle */}
          <div className="flex items-center gap-3">
            <Switch checked={amiConnected} onCheckedChange={setAmiConnected} id="ami-toggle" />
            <Label htmlFor="ami-toggle">AMI Connected</Label>
            <span className="text-xs text-muted-foreground">
              Asterisk Manager Interface link. When off, all outbound calls are blocked.
            </span>
          </div>

          {/* Queue Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-1 pr-2">
                    <div>Queue Name</div>
                    <div className="font-normal text-xs">Identifier for this call queue</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Calls Waiting</div>
                    <div className="font-normal text-xs">Inbound calls in queue</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Oldest Wait (s)</div>
                    <div className="font-normal text-xs">Longest caller wait time</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Agents Avail</div>
                    <div className="font-normal text-xs">Agents ready to take calls</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Agents In</div>
                    <div className="font-normal text-xs">Agents logged into queue</div>
                  </th>
                  <th className="pb-1"></th>
                </tr>
              </thead>
              <tbody>
                {queues.map((q, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 pr-2">
                      <Input
                        value={q.queue_name}
                        onChange={e => updateQueue(i, "queue_name", e.target.value)}
                        className="h-8"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.calls_waiting}
                        onChange={e => updateQueue(i, "calls_waiting", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.oldest_wait_seconds}
                        onChange={e => updateQueue(i, "oldest_wait_seconds", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.agents_available}
                        onChange={e => updateQueue(i, "agents_available", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.agents_logged_in}
                        onChange={e => updateQueue(i, "agents_logged_in", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                      />
                    </td>
                    <td className="py-2">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeQueue(i)}>
                        <Trash2 className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button variant="outline" size="sm" onClick={addQueue}>
            <Plus className="h-4 w-4 mr-1" />
            Add Queue
          </Button>
        </CardContent>
      </Card>

      {/* Section 2: Patient List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Patient List
              </CardTitle>
              <CardDescription>
                Mock patient records for the outbound call queue. Patients are sorted by priority bucket (1-4) based on their flags. Abandoned patients who have never been AI-called get highest priority.
              </CardDescription>
            </div>
            <Badge variant="secondary">{patients.length} patients</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-1 pr-2">
                    <div>Name</div>
                    <div className="font-normal text-xs">Patient full name</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Phone</div>
                    <div className="font-normal text-xs">Number to dial</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Language</div>
                    <div className="font-normal text-xs">Preferred language</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Abandoned</div>
                    <div className="font-normal text-xs">Previously abandoned a call</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Called In</div>
                    <div className="font-normal text-xs">Has called the clinic before</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>AI Called</div>
                    <div className="font-normal text-xs">Previously called by AI</div>
                  </th>
                  <th className="pb-1 pr-2">
                    <div>Attempts</div>
                    <div className="font-normal text-xs">Past call attempts</div>
                  </th>
                  <th className="pb-1"></th>
                </tr>
              </thead>
              <tbody>
                {patients.map((p, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 pr-2">
                      <Input
                        value={p.name}
                        onChange={e => updatePatient(i, "name", e.target.value)}
                        className="h-8"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        value={p.phone}
                        onChange={e => updatePatient(i, "phone", e.target.value)}
                        className="h-8 w-28"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Select value={p.language} onValueChange={v => updatePatient(i, "language", v)}>
                        <SelectTrigger className="h-8 w-20">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">EN</SelectItem>
                          <SelectItem value="es">ES</SelectItem>
                          <SelectItem value="zh">ZH</SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="py-2 pr-2 text-center">
                      <input
                        type="checkbox"
                        checked={p.has_abandoned_before}
                        onChange={e => updatePatient(i, "has_abandoned_before", e.target.checked)}
                        className="h-4 w-4"
                      />
                    </td>
                    <td className="py-2 pr-2 text-center">
                      <input
                        type="checkbox"
                        checked={p.has_called_in_before}
                        onChange={e => updatePatient(i, "has_called_in_before", e.target.checked)}
                        className="h-4 w-4"
                      />
                    </td>
                    <td className="py-2 pr-2 text-center">
                      <input
                        type="checkbox"
                        checked={p.ai_called_before}
                        onChange={e => updatePatient(i, "ai_called_before", e.target.checked)}
                        className="h-4 w-4"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={p.attempt_count}
                        onChange={e => updatePatient(i, "attempt_count", parseInt(e.target.value) || 0)}
                        className="h-8 w-16"
                      />
                    </td>
                    <td className="py-2">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removePatient(i)}>
                        <Trash2 className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button variant="outline" size="sm" onClick={addPatient}>
            <Plus className="h-4 w-4 mr-1" />
            Add Patient
          </Button>
        </CardContent>
      </Card>

      {/* Section 3: Dispatcher Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Dispatcher Settings
          </CardTitle>
          <CardDescription>
            Controls how the auto-call dispatcher evaluates gating conditions and selects patients. The dispatcher runs a polling loop that checks queue state, picks the next candidate, and signals the frontend to start a call.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label>Poll Interval (s)</Label>
              <Input
                type="number"
                min={1}
                value={dispatcher.poll_interval}
                onChange={e => updateDispatcher("poll_interval", parseInt(e.target.value) || 10)}
              />
              <p className="text-xs text-muted-foreground">
                Seconds between each dispatcher tick. Lower values make the dispatcher react faster.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Dispatch Timeout (s)</Label>
              <Input
                type="number"
                min={1}
                value={dispatcher.dispatch_timeout}
                onChange={e => updateDispatcher("dispatch_timeout", parseInt(e.target.value) || 30)}
              />
              <p className="text-xs text-muted-foreground">
                Max seconds to wait for the frontend to acknowledge a dispatched call before timing out.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Max Attempts</Label>
              <Input
                type="number"
                min={1}
                value={dispatcher.max_attempts}
                onChange={e => updateDispatcher("max_attempts", parseInt(e.target.value) || 3)}
              />
              <p className="text-xs text-muted-foreground">
                Maximum call attempts per patient. Patients at this limit are skipped.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Min Hours Between</Label>
              <Input
                type="number"
                min={0}
                value={dispatcher.min_hours_between}
                onChange={e => updateDispatcher("min_hours_between", parseInt(e.target.value) || 6)}
              />
              <p className="text-xs text-muted-foreground">
                Minimum hours between call attempts to the same patient. Prevents calling too frequently.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Apply Button */}
      <div className="flex justify-end">
        <Button size="lg" onClick={handleApply} disabled={applying}>
          <RotateCcw className={`h-4 w-4 mr-2 ${applying ? "animate-spin" : ""}`} />
          {applying ? "Applying..." : "Apply & Restart Simulation"}
        </Button>
      </div>
    </div>
  );
}
