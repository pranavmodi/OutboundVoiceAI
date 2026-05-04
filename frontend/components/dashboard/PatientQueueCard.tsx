"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Users, Phone, RefreshCw, UserRound, Clock, RotateCcw, Pencil, Trash2 } from "lucide-react";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import type { Patient } from "@/types";

interface PatientQueueCardProps {
  patients: Patient[];
  onCallPatient: (patientId: string) => void;
  onRefresh: () => void;
  onReloadScenario?: () => void;
  loading?: boolean;
  onDeletePatient?: (patientId: string) => Promise<void>;
  onUpdatePatient?: (patientId: string, data: {
    name?: string;
    phone?: string;
    language?: string;
    has_abandoned_before?: boolean;
    has_called_in_before?: boolean;
    ai_called_before?: boolean;
    attempt_count?: number;
  }) => Promise<void>;
  isCallActive: boolean;
  outboundAllowed: boolean;
  source?: "simulation" | "live";
  lastUpdated?: Date | null;
  // Phase 7: live in-flight calls reported by the dispatcher tick.
  activeCalls?: Array<{
    patient_id: string;
    patient_name: string;
    phase: "dispatched" | "active" | "voicemail";
    call_id: string | null;
  }>;
  maxParallelCalls?: number;
}

const statusColors: Record<string, "destructive" | "warning" | "secondary" | "outline"> = {
  "Ordered": "destructive",
  "No Show": "warning",
  "Needs to Reschedule": "secondary",
  "Couldnt Schedule": "outline",
};

function formatLastUpdated(date: Date | null | undefined): string {
  if (!date) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  return date.toLocaleTimeString();
}

export function PatientQueueCard({
  patients,
  onCallPatient,
  onRefresh,
  onReloadScenario,
  onDeletePatient,
  onUpdatePatient,
  isCallActive,
  outboundAllowed,
  loading,
  source = "simulation",
  lastUpdated,
  activeCalls = [],
  maxParallelCalls = 1,
}: PatientQueueCardProps) {
  const [editingPatient, setEditingPatient] = useState<Patient | null>(null);
  const [editForm, setEditForm] = useState({
    name: "",
    phone: "",
    language: "en",
    has_abandoned_before: false,
    has_called_in_before: false,
    ai_called_before: false,
    attempt_count: 0,
  });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleEditClick = (patient: Patient) => {
    setEditingPatient(patient);
    setEditForm({
      name: patient.name,
      phone: patient.phone,
      language: patient.language,
      has_abandoned_before: patient.has_abandoned_before,
      has_called_in_before: patient.has_called_in_before,
      ai_called_before: patient.ai_called_before,
      attempt_count: patient.attempt_count,
    });
  };

  const handleSaveEdit = async () => {
    if (!editingPatient || !onUpdatePatient) return;
    setSaving(true);
    try {
      await onUpdatePatient(editingPatient.patient_id, editForm);
      setEditingPatient(null);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (patientId: string) => {
    if (!onDeletePatient) return;
    if (!confirm("Delete this patient?")) return;
    setDeleting(patientId);
    try {
      await onDeletePatient(patientId);
    } finally {
      setDeleting(null);
    }
  };

  const isSimulation = source === "simulation";

  return (
    <>
      {/* Edit Patient Dialog */}
      <Dialog open={!!editingPatient} onOpenChange={(open) => !open && setEditingPatient(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Patient</DialogTitle>
            <DialogDescription>
              Update patient information. Changes will be saved to the active scenario.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-phone">Phone</Label>
              <Input
                id="edit-phone"
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label>Language</Label>
              <Select
                value={editForm.language}
                onValueChange={(v) => setEditForm({ ...editForm, language: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="es">Spanish</SelectItem>
                  <SelectItem value="zh">Chinese</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-attempts">Attempt Count</Label>
              <Input
                id="edit-attempts"
                type="number"
                min={0}
                value={editForm.attempt_count}
                onChange={(e) => setEditForm({ ...editForm, attempt_count: parseInt(e.target.value) || 0 })}
              />
            </div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={editForm.has_abandoned_before}
                  onChange={(e) => setEditForm({ ...editForm, has_abandoned_before: e.target.checked })}
                  className="h-4 w-4"
                />
                Has abandoned
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={editForm.has_called_in_before}
                  onChange={(e) => setEditForm({ ...editForm, has_called_in_before: e.target.checked })}
                  className="h-4 w-4"
                />
                Has called in
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={editForm.ai_called_before}
                  onChange={(e) => setEditForm({ ...editForm, ai_called_before: e.target.checked })}
                  className="h-4 w-4"
                />
                AI called
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingPatient(null)}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Main Card */}
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Users className="h-5 w-5" />
            Outbound Queue
            <InfoTooltip content="Patients awaiting outbound calls. Ordered by RadFlow status (Ordered → No Show → Needs to Reschedule), then by fewest total attempts (AI + human). At max attempts, status flips to Couldnt Schedule and the patient leaves the queue." />
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge
              variant={source === "live" ? "default" : "secondary"}
              className="text-xs"
            >
              {source === "live" ? "Live RadFlow" : "Simulation"}
            </Badge>
            <Badge variant="outline" className="tabular-nums text-xs">
              {patients.length} patient{patients.length !== 1 ? "s" : ""}
            </Badge>
            {source === "simulation" && onReloadScenario && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={onReloadScenario}
                title="Reload scenario (reset patients)"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onRefresh} title="Refresh">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
        {lastUpdated && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
            <Clock className="h-3 w-3" />
            Updated {formatLastUpdated(lastUpdated)}
          </div>
        )}
        {maxParallelCalls > 1 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">
              Active calls {activeCalls.filter((c) => c.phase !== "voicemail").length}/{maxParallelCalls}
            </span>
            {activeCalls.map((c) => (
              <Badge
                key={c.patient_id}
                variant={c.phase === "voicemail" ? "secondary" : c.phase === "active" ? "default" : "outline"}
                className="text-[10px] tabular-nums"
                title={`call_id=${c.call_id ?? "(pending)"}`}
              >
                {c.patient_name || c.patient_id}
                {c.phase === "voicemail" && " · VM"}
                {c.phase === "dispatched" && " · dialing"}
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-[400px]">
          <div className="space-y-1.5 px-6 pb-6">
            {loading ? (
              <div className="space-y-2">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg bg-muted/40 px-3 py-2.5">
                    <Skeleton className="h-4 w-4 shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                    <Skeleton className="h-8 w-16" />
                  </div>
                ))}
              </div>
            ) : patients.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <UserRound className="h-10 w-10 mb-3 opacity-20" />
                <p className="text-sm font-medium">No patients in queue</p>
                <p className="text-xs mt-1">Patients will appear here when added</p>
              </div>
            ) : (
              patients.map((patient, index) => (
                <div
                  key={patient.patient_id}
                  className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2.5 hover:bg-muted/70 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-muted-foreground tabular-nums w-5">
                        {index + 1}
                      </span>
                      <span className="text-sm font-medium truncate">{patient.name}</span>
                      {patient.radflow_status && (
                        <Badge
                          variant={statusColors[patient.radflow_status] || "outline"}
                          className="text-[10px] px-1.5 py-0"
                        >
                          {patient.radflow_status}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2.5 mt-1 ml-7 text-xs text-muted-foreground">
                      <span className="font-mono">{patient.patient_id}</span>
                      <span className="tabular-nums">{patient.phone}</span>
                      <span className="uppercase font-medium">{patient.language}</span>
                      <span className="tabular-nums" title="Total attempts (AI + human)">
                        {patient.total_attempts ?? patient.attempt_count ?? 0} total
                        {" "}(AI {patient.ai_attempt_count ?? 0} / human {patient.human_attempt_count ?? 0})
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3 shrink-0">
                    {isSimulation && onUpdatePatient && (
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => handleEditClick(patient)}
                        className="h-8 w-8"
                        title="Edit patient"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    {isSimulation && onDeletePatient && (
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => handleDelete(patient.patient_id)}
                        disabled={deleting === patient.patient_id}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        title="Delete patient"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onCallPatient(patient.patient_id)}
                      disabled={isCallActive || !outboundAllowed}
                      className="h-8 text-xs"
                    >
                      <Phone className="h-3 w-3 mr-1.5" />
                      Call
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
    </>
  );
}
