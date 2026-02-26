"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  History,
  RefreshCw,
  Phone,
  PhoneForwarded,
  PhoneMissed,
  PhoneOff,
  MessageSquare,
  User,
  Bot,
  CalendarDays,
  NotebookPen,
} from "lucide-react";
import { formatDate, formatTime, formatDuration } from "@/lib/utils";
import type { CallLog } from "@/types";

interface CallHistoryCardProps {
  calls: CallLog[];
  onRefresh: () => void;
}

const outcomeConfig: Record<
  string,
  { label: string; icon: typeof Phone; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }
> = {
  transferred: { label: "Transferred", icon: PhoneForwarded, variant: "success" },
  callback_requested: { label: "Callback", icon: MessageSquare, variant: "secondary" },
  no_answer: { label: "No Answer", icon: PhoneMissed, variant: "warning" },
  voicemail: { label: "Voicemail", icon: MessageSquare, variant: "warning" },
  wrong_number: { label: "Wrong Number", icon: PhoneOff, variant: "destructive" },
  disconnected: { label: "Disconnected", icon: PhoneOff, variant: "destructive" },
  completed: { label: "Completed", icon: Phone, variant: "default" },
  failed: { label: "Failed", icon: PhoneOff, variant: "destructive" },
  in_progress: { label: "In Progress", icon: Phone, variant: "default" },
};

interface GroupedCalls {
  dateKey: string;
  dateLabel: string;
  calls: CallLog[];
}

function inferPreferredCallbackFromTranscript(call: CallLog): string | null {
  if (!call.transcript?.length) return null;

  // Prefer explicit system capture message if present.
  const systemCapture = call.transcript.find(
    (entry) =>
      entry.speaker === "system" &&
      entry.text.toLowerCase().startsWith("preferred callback captured:")
  );
  if (systemCapture) {
    return systemCapture.text.split(":").slice(1).join(":").trim() || null;
  }

  // Fallback: look at recent patient/AI text for callback-time language.
  const recent = call.transcript.slice(-8).map((t) => t.text.toLowerCase());
  const marker = recent.find(
    (t) =>
      (t.includes("call me") || t.includes("call you back") || t.includes("callback")) &&
      (t.includes("tomorrow") || t.includes("today") || t.includes("pm") || t.includes("am") || t.includes("hour") || t.includes("minute"))
  );
  if (marker) return marker;
  return null;
}

function getDateKeyFromCall(call: CallLog): string {
  const source = call.started_at || call.ended_at;
  if (!source) return "unknown-date";
  const d = new Date(source);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function getDateLabel(dateKey: string): string {
  if (dateKey === "unknown-date") return "Unknown Date";
  const date = new Date(`${dateKey}T00:00:00`);
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
    today.getDate()
  ).padStart(2, "0")}`;
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const yesterdayKey = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(
    yesterday.getDate()
  ).padStart(2, "0")}`;

  if (dateKey === todayKey) return "Today";
  if (dateKey === yesterdayKey) return "Yesterday";
  return formatDate(date);
}

export function CallHistoryCard({ calls, onRefresh }: CallHistoryCardProps) {
  const [selectedCall, setSelectedCall] = useState<CallLog | null>(null);
  const groupedCalls: GroupedCalls[] = [];
  const byDate = new Map<string, CallLog[]>();
  for (const call of calls) {
    const key = getDateKeyFromCall(call);
    const existing = byDate.get(key) || [];
    existing.push(call);
    byDate.set(key, existing);
  }
  const sortedKeys = Array.from(byDate.keys()).sort((a, b) => (a < b ? 1 : -1));
  for (const key of sortedKeys) {
    groupedCalls.push({
      dateKey: key,
      dateLabel: getDateLabel(key),
      calls: byDate.get(key) || [],
    });
  }

  const callNotes: string[] = [];
  const selectedPreferred =
    selectedCall?.preferred_callback_time || (selectedCall ? inferPreferredCallbackFromTranscript(selectedCall) : null);
  if (selectedPreferred) {
    callNotes.push(`Patient preferred callback time: ${selectedPreferred}`);
  } else if (selectedCall?.outcome === "callback_requested") {
    callNotes.push("Patient requested a callback.");
  }
  if (selectedCall?.error_message) {
    callNotes.push(`Call issue: ${selectedCall.error_message}`);
  }

  return (
    <>
      <Card className="flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <History className="h-5 w-5" />
              Call History
            </CardTitle>
            <div className="flex items-center gap-2">
              {calls.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {calls.length} call{calls.length !== 1 ? "s" : ""}
                </span>
              )}
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onRefresh}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 p-0">
          <ScrollArea className="h-[300px]">
            <div className="space-y-1.5 px-6 pb-6">
              {calls.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <History className="h-10 w-10 mb-3 opacity-15" />
                  <p className="text-sm font-medium">No calls yet</p>
                  <p className="text-xs mt-1">Completed calls will appear here</p>
                </div>
              ) : (
                groupedCalls.map((group) => (
                  <div key={group.dateKey} className="space-y-1.5">
                    <div className="sticky top-0 z-10 bg-background/80 backdrop-blur px-1 py-1 rounded">
                      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                        <CalendarDays className="h-3 w-3" />
                        {group.dateLabel}
                      </p>
                    </div>
                    {group.calls.map((call) => {
                      const config = outcomeConfig[call.outcome] || outcomeConfig.completed;
                      const Icon = config.icon;

                      return (
                        <button
                          key={call.call_id}
                          onClick={() => setSelectedCall(call)}
                          className="w-full flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2.5 hover:bg-muted/70 transition-colors text-left"
                        >
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-background">
                              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                            <div>
                              <p className="text-sm font-medium">{call.patient_name}</p>
                              <p className="text-xs text-muted-foreground tabular-nums">
                                {call.started_at ? formatTime(call.started_at) : "—"} • {call.phone || "No phone"}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2.5">
                            <div className="text-right">
                              <div className="flex items-center justify-end gap-2.5">
                                <span className="text-xs text-muted-foreground tabular-nums">
                                  {formatDuration(call.duration_seconds)}
                                </span>
                                <Badge variant={config.variant} className="text-[10px] px-1.5 py-0">
                                  {config.label}
                                </Badge>
                              </div>
                              {(call.preferred_callback_time || inferPreferredCallbackFromTranscript(call)) && (
                                <p className="mt-1 text-[11px] text-muted-foreground flex items-center justify-end gap-1">
                                  <NotebookPen className="h-3 w-3" />
                                  Preferred callback: {call.preferred_callback_time || inferPreferredCallbackFromTranscript(call)}
                                </p>
                              )}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Call Detail Dialog */}
      <Dialog open={!!selectedCall} onOpenChange={() => setSelectedCall(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-lg">Call Details</DialogTitle>
          </DialogHeader>
          {selectedCall && (
            <div className="flex-1 overflow-auto space-y-4">
              {/* Call Info */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Patient</p>
                  <p className="text-sm font-medium mt-0.5">{selectedCall.patient_name}</p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Patient ID</p>
                  <p className="text-sm font-medium mt-0.5">{selectedCall.patient_id || "—"}</p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Phone</p>
                  <p className="text-sm font-medium mt-0.5 tabular-nums">{selectedCall.phone}</p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Order ID</p>
                  <p className="text-sm font-medium mt-0.5">{selectedCall.order_id || "—"}</p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Duration</p>
                  <p className="text-sm font-medium mt-0.5 tabular-nums">{formatDuration(selectedCall.duration_seconds)}</p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Outcome</p>
                  <div className="mt-1">
                    <Badge variant={outcomeConfig[selectedCall.outcome]?.variant || "default"} className="text-xs">
                      {outcomeConfig[selectedCall.outcome]?.label || selectedCall.outcome}
                    </Badge>
                  </div>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Call Time</p>
                  <p className="text-sm font-medium mt-0.5 tabular-nums">
                    {selectedCall.started_at
                      ? `${formatDate(selectedCall.started_at)} ${formatTime(selectedCall.started_at)}`
                      : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Priority</p>
                  <p className="text-sm font-medium mt-0.5">Bucket {selectedCall.priority_bucket}</p>
                </div>
              </div>

              {/* Call Notes */}
              {callNotes.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                    Call Notes
                  </h4>
                  <div className="rounded-lg border bg-muted/20 p-3 space-y-1.5">
                    {callNotes.map((note, idx) => (
                      <p key={idx} className="text-sm">
                        {note}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions Taken */}
              {(selectedCall.transfer_attempted || selectedCall.voicemail_left || selectedCall.sms_sent) && (
                <div className="flex gap-2">
                  {selectedCall.transfer_attempted && (
                    <Badge variant={selectedCall.transfer_success ? "success" : "warning"} className="text-xs">
                      Transfer {selectedCall.transfer_success ? "Success" : "Attempted"}
                    </Badge>
                  )}
                  {selectedCall.voicemail_left && <Badge variant="secondary" className="text-xs">VM Left</Badge>}
                  {selectedCall.sms_sent && <Badge variant="secondary" className="text-xs">SMS Sent</Badge>}
                </div>
              )}

              <Separator />

              {/* Transcript */}
              <div>
                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Transcript</h4>
                <ScrollArea className="h-[250px] rounded-lg border bg-muted/20 p-3">
                  <div className="space-y-2.5">
                    {selectedCall.transcript.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-6">
                        No transcript available
                      </p>
                    ) : (
                      selectedCall.transcript.map((entry, index) => (
                        <div
                          key={index}
                          className={`flex gap-2 ${entry.speaker === "patient" ? "justify-end" : "justify-start"}`}
                        >
                          {entry.speaker === "ai" && (
                            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                              <Bot className="h-3 w-3" />
                            </div>
                          )}
                          <div
                            className={`rounded-lg px-3 py-1.5 text-sm max-w-[80%] ${
                              entry.speaker === "ai"
                                ? "bg-muted"
                                : entry.speaker === "patient"
                                  ? "bg-primary text-primary-foreground"
                                  : "bg-amber-100 text-amber-900 border border-amber-200"
                            }`}
                          >
                            <p>{entry.text}</p>
                            <p className="text-[10px] opacity-70 mt-1 tabular-nums">
                              {entry.timestamp ? formatTime(entry.timestamp) : ""}
                            </p>
                          </div>
                          {entry.speaker === "patient" && (
                            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary">
                              <User className="h-3 w-3" />
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
