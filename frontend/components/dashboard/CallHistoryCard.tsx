"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
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
            <Button variant="ghost" size="icon" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex-1 p-0">
          <ScrollArea className="h-[300px]">
            <div className="space-y-1 p-4 pt-0">
              {calls.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No calls yet
                </p>
              ) : (
                calls.map((call) => {
                  const config = outcomeConfig[call.outcome] || outcomeConfig.completed;
                  const Icon = config.icon;

                  return (
                    <button
                      key={call.call_id}
                      onClick={() => setSelectedCall(call)}
                      className="w-full flex items-center justify-between rounded-md border p-3 hover:bg-muted/50 transition-colors text-left"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="font-medium">{call.patient_name}</p>
                          <p className="text-sm text-muted-foreground">
                            {call.started_at ? formatTime(call.started_at) : "—"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">
                          {formatDuration(call.duration_seconds)}
                        </span>
                        <Badge variant={config.variant}>{config.label}</Badge>
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
            <DialogTitle>Call Details</DialogTitle>
          </DialogHeader>
          {selectedCall && (
            <div className="flex-1 overflow-auto space-y-4">
              {/* Call Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Patient</p>
                  <p className="font-medium">{selectedCall.patient_name}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Phone</p>
                  <p className="font-medium">{selectedCall.phone}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Duration</p>
                  <p className="font-medium">{formatDuration(selectedCall.duration_seconds)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Outcome</p>
                  <Badge variant={outcomeConfig[selectedCall.outcome]?.variant || "default"}>
                    {outcomeConfig[selectedCall.outcome]?.label || selectedCall.outcome}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Started</p>
                  <p className="font-medium">
                    {selectedCall.started_at ? formatTime(selectedCall.started_at) : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Priority</p>
                  <p className="font-medium">Bucket {selectedCall.priority_bucket}</p>
                </div>
              </div>

              {/* Actions Taken */}
              <div className="flex gap-2">
                {selectedCall.transfer_attempted && (
                  <Badge variant={selectedCall.transfer_success ? "success" : "warning"}>
                    Transfer {selectedCall.transfer_success ? "Success" : "Attempted"}
                  </Badge>
                )}
                {selectedCall.voicemail_left && <Badge variant="secondary">VM Left</Badge>}
                {selectedCall.sms_sent && <Badge variant="secondary">SMS Sent</Badge>}
              </div>

              {/* Transcript */}
              <div>
                <p className="text-sm font-medium mb-2">Transcript</p>
                <ScrollArea className="h-[250px] rounded-md border p-3">
                  <div className="space-y-3">
                    {selectedCall.transcript.length === 0 ? (
                      <p className="text-sm text-muted-foreground text-center py-4">
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
                            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                              <Bot className="h-3 w-3" />
                            </div>
                          )}
                          <div
                            className={`rounded-lg px-3 py-2 text-sm max-w-[80%] ${
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
