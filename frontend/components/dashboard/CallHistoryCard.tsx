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
} from "lucide-react";
import { formatTime, formatDuration } from "@/lib/utils";
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

export function CallHistoryCard({ calls, onRefresh }: CallHistoryCardProps) {
  const [selectedCall, setSelectedCall] = useState<CallLog | null>(null);

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
                calls.map((call) => {
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
                            {call.started_at ? formatTime(call.started_at) : "—"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {formatDuration(call.duration_seconds)}
                        </span>
                        <Badge variant={config.variant} className="text-[10px] px-1.5 py-0">
                          {config.label}
                        </Badge>
                      </div>
                    </button>
                  );
                })
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
                  <p className="text-xs text-muted-foreground">Phone</p>
                  <p className="text-sm font-medium mt-0.5 tabular-nums">{selectedCall.phone}</p>
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
                  <p className="text-xs text-muted-foreground">Started</p>
                  <p className="text-sm font-medium mt-0.5 tabular-nums">
                    {selectedCall.started_at ? formatTime(selectedCall.started_at) : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">Priority</p>
                  <p className="text-sm font-medium mt-0.5">Bucket {selectedCall.priority_bucket}</p>
                </div>
              </div>

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
                          className={`flex gap-2 ${
                            entry.speaker === "ai" ? "justify-start" : "justify-end"
                          }`}
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
                                : "bg-primary text-primary-foreground"
                            }`}
                          >
                            {entry.text}
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
