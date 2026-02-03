"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  Plus,
  Trash2,
  Save,
  Copy,
  Settings2,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { SimulationScenario, ScenarioPatient, QueueInfo } from "@/types";

interface QueueRow {
  Queue: string;
  Calls: number;
  Holdtime: number;
  AvailableAgents: number;
}

interface SimulationConsoleProps {
  scenarios: SimulationScenario[];
  activeScenarioId: string | null;
  onSaveScenario: (id: string, data: {
    label?: string;
    description?: string;
    ami_connected?: boolean;
    queues?: QueueRow[];
    patients?: ScenarioPatient[];
  }) => Promise<SimulationScenario | null>;
  onCreateScenario: (data: {
    label: string;
    description?: string;
    ami_connected?: boolean;
    queues?: QueueRow[];
    patients?: ScenarioPatient[];
  }) => Promise<SimulationScenario | null>;
  onDeleteScenario: (id: string) => Promise<boolean>;
  onRefreshScenarios: () => Promise<void>;
}

function mkQueue(Queue: string, overrides: Partial<QueueRow> = {}): QueueRow {
  return {
    Queue,
    Calls: 0,
    Holdtime: 0,
    AvailableAgents: 0,
    ...overrides,
  };
}

function mkPatient(overrides: Partial<ScenarioPatient> = {}): ScenarioPatient {
  return {
    name: "",
    phone: "",
    language: "en",
    has_abandoned_before: false,
    has_called_in_before: false,
    ai_called_before: false,
    attempt_count: 0,
    ...overrides,
  };
}

export function SimulationConsole({
  scenarios,
  activeScenarioId,
  onSaveScenario,
  onCreateScenario,
  onDeleteScenario,
  onRefreshScenarios,
}: SimulationConsoleProps) {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [amiConnected, setAmiConnected] = useState(true);
  const [queues, setQueues] = useState<QueueRow[]>([]);
  const [patients, setPatients] = useState<ScenarioPatient[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const selectedScenario = scenarios.find(s => s.id === selectedScenarioId);
  const isBuiltin = selectedScenario?.is_builtin ?? false;

  // Load scenario data when selection changes
  const loadScenario = useCallback((scenario: SimulationScenario) => {
    setLabel(scenario.label);
    setDescription(scenario.description);
    setAmiConnected(scenario.ami_connected);
    setQueues((scenario.queues || []).map(q => ({
      Queue: q.Queue || "",
      Calls: q.Calls || 0,
      Holdtime: q.Holdtime || 0,
      AvailableAgents: q.AvailableAgents || 0,
    })));
    setPatients((scenario.patients || []).map(p => ({ ...mkPatient(), ...p })));
    setIsDirty(false);
    setFeedback(null);
  }, []);

  // Initialize with first scenario or active scenario
  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenarioId) {
      const initialId = activeScenarioId || scenarios[0].id;
      setSelectedScenarioId(initialId);
      const scenario = scenarios.find(s => s.id === initialId);
      if (scenario) loadScenario(scenario);
    }
  }, [scenarios, activeScenarioId, selectedScenarioId, loadScenario]);

  const handleSelectScenario = (scenarioId: string) => {
    const scenario = scenarios.find(s => s.id === scenarioId);
    if (scenario) {
      setSelectedScenarioId(scenarioId);
      loadScenario(scenario);
    }
  };

  // Queue handlers
  const updateQueue = (index: number, field: keyof QueueRow, value: string | number) => {
    setQueues(prev => prev.map((q, i) => i === index ? { ...q, [field]: value } : q));
    setIsDirty(true);
  };

  const addQueue = () => {
    setQueues(prev => [...prev, mkQueue("")]);
    setIsDirty(true);
  };

  const removeQueue = (index: number) => {
    setQueues(prev => prev.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  // Patient handlers
  const updatePatient = (index: number, field: keyof ScenarioPatient, value: string | number | boolean) => {
    setPatients(prev => prev.map((p, i) => i === index ? { ...p, [field]: value } : p));
    setIsDirty(true);
  };

  const addPatient = () => {
    setPatients(prev => [...prev, mkPatient()]);
    setIsDirty(true);
  };

  const removePatient = (index: number) => {
    setPatients(prev => prev.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const handleFieldChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setter(e.target.value);
    setIsDirty(true);
  };

  // Save existing scenario (only for custom scenarios)
  const handleSave = async () => {
    if (!selectedScenarioId || isBuiltin) return;
    setSaving(true);
    setFeedback(null);
    try {
      const result = await onSaveScenario(selectedScenarioId, {
        label,
        description,
        ami_connected: amiConnected,
        queues,
        patients,
      });
      if (result) {
        setFeedback({ type: "success", message: "Scenario saved successfully." });
        setIsDirty(false);
        await onRefreshScenarios();
      } else {
        setFeedback({ type: "error", message: "Failed to save scenario." });
      }
    } catch {
      setFeedback({ type: "error", message: "Failed to save scenario." });
    } finally {
      setSaving(false);
    }
  };

  // Save as new scenario
  const handleSaveAsNew = async () => {
    setSaving(true);
    setFeedback(null);
    try {
      const result = await onCreateScenario({
        label: label + " (Copy)",
        description,
        ami_connected: amiConnected,
        queues,
        patients,
      });
      if (result) {
        setFeedback({ type: "success", message: "New scenario created successfully." });
        await onRefreshScenarios();
        // Select the new scenario
        setSelectedScenarioId(result.id);
        setLabel(result.label);
        setIsDirty(false);
      } else {
        setFeedback({ type: "error", message: "Failed to create scenario." });
      }
    } catch {
      setFeedback({ type: "error", message: "Failed to create scenario." });
    } finally {
      setSaving(false);
    }
  };

  // Delete scenario
  const handleDelete = async () => {
    if (!selectedScenarioId || isBuiltin) return;
    if (!confirm("Are you sure you want to delete this scenario?")) return;
    setSaving(true);
    setFeedback(null);
    try {
      const success = await onDeleteScenario(selectedScenarioId);
      if (success) {
        setFeedback({ type: "success", message: "Scenario deleted." });
        await onRefreshScenarios();
        // Select first available scenario
        const remaining = scenarios.filter(s => s.id !== selectedScenarioId);
        if (remaining.length > 0) {
          setSelectedScenarioId(remaining[0].id);
          loadScenario(remaining[0]);
        }
      } else {
        setFeedback({ type: "error", message: "Failed to delete scenario." });
      }
    } catch {
      setFeedback({ type: "error", message: "Failed to delete scenario." });
    } finally {
      setSaving(false);
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

      {/* Scenario Selector and Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Scenario Editor
          </CardTitle>
          <CardDescription>
            Edit simulation scenarios. Builtins are read-only — use "Save As New" to create a custom copy.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 space-y-1.5">
              <Label>Select Scenario</Label>
              <Select value={selectedScenarioId} onValueChange={handleSelectScenario}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a scenario..." />
                </SelectTrigger>
                <SelectContent>
                  {scenarios.map(s => (
                    <SelectItem key={s.id} value={s.id}>
                      <span className="flex items-center gap-2">
                        {s.label}
                        {s.is_builtin && <Badge variant="outline" className="text-xs">Builtin</Badge>}
                        {s.id === activeScenarioId && <Badge variant="success" className="text-xs">Active</Badge>}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="scenario-label">Label</Label>
              <Input
                id="scenario-label"
                value={label}
                onChange={handleFieldChange(setLabel)}
                disabled={isBuiltin}
                placeholder="Scenario name"
              />
            </div>
            <div className="space-y-1.5">
              <Label>AMI Connection</Label>
              <div className="flex items-center gap-2 pt-2">
                <Button
                  variant={amiConnected ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setAmiConnected(true); setIsDirty(true); }}
                  disabled={isBuiltin}
                >
                  <Wifi className="h-4 w-4 mr-1" />
                  Connected
                </Button>
                <Button
                  variant={!amiConnected ? "destructive" : "outline"}
                  size="sm"
                  onClick={() => { setAmiConnected(false); setIsDirty(true); }}
                  disabled={isBuiltin}
                >
                  <WifiOff className="h-4 w-4 mr-1" />
                  Disconnected
                </Button>
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="scenario-description">Description</Label>
            <Textarea
              id="scenario-description"
              value={description}
              onChange={handleFieldChange(setDescription)}
              disabled={isBuiltin}
              placeholder="Describe this scenario..."
              rows={2}
            />
          </div>
        </CardContent>
      </Card>

      {/* Queue Configuration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Phone className="h-5 w-5" />
                Queue Configuration
              </CardTitle>
              <CardDescription>
                Simulates FreePBX/Asterisk call queues. The dispatcher checks these metrics each tick.
              </CardDescription>
            </div>
            <Badge variant="secondary">{queues.length} queues</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-1 pr-2">Queue</th>
                  <th className="pb-1 pr-2">Calls</th>
                  <th className="pb-1 pr-2">Holdtime (s)</th>
                  <th className="pb-1 pr-2">Avail Agents</th>
                  <th className="pb-1"></th>
                </tr>
              </thead>
              <tbody>
                {queues.map((q, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 pr-2">
                      <Input
                        value={q.Queue}
                        onChange={e => updateQueue(i, "Queue", e.target.value)}
                        className="h-8"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.Calls}
                        onChange={e => updateQueue(i, "Calls", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.Holdtime}
                        onChange={e => updateQueue(i, "Holdtime", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={q.AvailableAgents}
                        onChange={e => updateQueue(i, "AvailableAgents", parseInt(e.target.value) || 0)}
                        className="h-8 w-20"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2">
                      {!isBuiltin && (
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeQueue(i)}>
                          <Trash2 className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!isBuiltin && (
            <Button variant="outline" size="sm" onClick={addQueue}>
              <Plus className="h-4 w-4 mr-1" />
              Add Queue
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Patient List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Patient List
              </CardTitle>
              <CardDescription>
                Mock patient records for the outbound call queue.
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
                  <th className="pb-1 pr-2">Name</th>
                  <th className="pb-1 pr-2">Phone</th>
                  <th className="pb-1 pr-2">Lang</th>
                  <th className="pb-1 pr-2">Aband.</th>
                  <th className="pb-1 pr-2">Called</th>
                  <th className="pb-1 pr-2">AI</th>
                  <th className="pb-1 pr-2">Att.</th>
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
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        value={p.phone}
                        onChange={e => updatePatient(i, "phone", e.target.value)}
                        className="h-8 w-28"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Select
                        value={p.language}
                        onValueChange={v => updatePatient(i, "language", v)}
                        disabled={isBuiltin}
                      >
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
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2 text-center">
                      <input
                        type="checkbox"
                        checked={p.has_called_in_before}
                        onChange={e => updatePatient(i, "has_called_in_before", e.target.checked)}
                        className="h-4 w-4"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2 text-center">
                      <input
                        type="checkbox"
                        checked={p.ai_called_before}
                        onChange={e => updatePatient(i, "ai_called_before", e.target.checked)}
                        className="h-4 w-4"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="number"
                        min={0}
                        value={p.attempt_count}
                        onChange={e => updatePatient(i, "attempt_count", parseInt(e.target.value) || 0)}
                        className="h-8 w-16"
                        disabled={isBuiltin}
                      />
                    </td>
                    <td className="py-2">
                      {!isBuiltin && (
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removePatient(i)}>
                          <Trash2 className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!isBuiltin && (
            <Button variant="outline" size="sm" onClick={addPatient}>
              <Plus className="h-4 w-4 mr-1" />
              Add Patient
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex justify-end gap-3">
        {!isBuiltin && (
          <Button variant="destructive" size="sm" onClick={handleDelete} disabled={saving}>
            <Trash2 className="h-4 w-4 mr-1" />
            Delete
          </Button>
        )}
        <Button variant="outline" onClick={handleSaveAsNew} disabled={saving}>
          <Copy className="h-4 w-4 mr-1" />
          Save As New
        </Button>
        {!isBuiltin && (
          <Button onClick={handleSave} disabled={saving || !isDirty}>
            <Save className="h-4 w-4 mr-1" />
            {saving ? "Saving..." : "Save"}
          </Button>
        )}
      </div>
    </div>
  );
}
