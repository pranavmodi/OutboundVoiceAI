"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Users, Phone, RefreshCw, UserRound, Clock } from "lucide-react";
import type { Patient } from "@/types";

interface PatientQueueCardProps {
  patients: Patient[];
  onCallPatient: (patientId: string) => void;
  onRefresh: () => void;
  isCallActive: boolean;
  outboundAllowed: boolean;
  source?: "simulation" | "live";
  lastUpdated?: Date | null;
}

const priorityLabels: Record<number, string> = {
  1: "Abandoned, No AI Call",
  2: "Abandoned, AI Called",
  3: "No AI Call, Called In",
  4: "No AI Call, Never Called",
};

const priorityColors: Record<number, "destructive" | "warning" | "secondary" | "outline"> = {
  1: "destructive",
  2: "warning",
  3: "secondary",
  4: "outline",
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
  isCallActive,
  outboundAllowed,
  source = "simulation",
  lastUpdated,
}: PatientQueueCardProps) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Users className="h-5 w-5" />
            Outbound Queue
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
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onRefresh}>
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
      </CardHeader>
      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-[400px]">
          <div className="space-y-1.5 px-6 pb-6">
            {patients.length === 0 ? (
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
                      <Badge variant={priorityColors[patient.priority_bucket]} className="text-[10px] px-1.5 py-0">
                        P{patient.priority_bucket}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2.5 mt-1 ml-7 text-xs text-muted-foreground">
                      <span className="tabular-nums">{patient.phone}</span>
                      <span className="uppercase font-medium">{patient.language}</span>
                      {patient.attempt_count > 0 && (
                        <span className="tabular-nums">{patient.attempt_count} attempt{patient.attempt_count !== 1 ? "s" : ""}</span>
                      )}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onCallPatient(patient.patient_id)}
                    disabled={isCallActive || !outboundAllowed}
                    className="ml-3 shrink-0 h-8 text-xs"
                  >
                    <Phone className="h-3 w-3 mr-1.5" />
                    Call
                  </Button>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
