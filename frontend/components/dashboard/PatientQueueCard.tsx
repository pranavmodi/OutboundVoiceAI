"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Users, Phone, RefreshCw } from "lucide-react";
import type { Patient } from "@/types";

interface PatientQueueCardProps {
  patients: Patient[];
  onCallPatient: (patientId: string) => void;
  onRefresh: () => void;
  isCallActive: boolean;
  outboundAllowed: boolean;
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

export function PatientQueueCard({
  patients,
  onCallPatient,
  onRefresh,
  isCallActive,
  outboundAllowed,
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
            <Badge variant="secondary">{patients.length} patients</Badge>
            <Button variant="ghost" size="icon" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-[400px]">
          <div className="space-y-1 p-4 pt-0">
            {patients.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">
                No patients in queue
              </p>
            ) : (
              patients.map((patient, index) => (
                <div
                  key={patient.patient_id}
                  className="flex items-center justify-between rounded-md border p-3 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">#{index + 1}</span>
                      <span className="font-medium truncate">{patient.name}</span>
                      <Badge variant={priorityColors[patient.priority_bucket]} className="text-xs">
                        P{patient.priority_bucket}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
                      <span>{patient.phone}</span>
                      <span className="uppercase">{patient.language}</span>
                      {patient.attempt_count > 0 && (
                        <span>{patient.attempt_count} attempts</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {priorityLabels[patient.priority_bucket]}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => onCallPatient(patient.patient_id)}
                    disabled={isCallActive || !outboundAllowed}
                    className="ml-2 shrink-0"
                  >
                    <Phone className="h-4 w-4 mr-1" />
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
