"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Phone,
  Wifi,
  WifiOff,
  Users,
  RotateCcw,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type { QueueState, Patient } from "@/types";

interface SimulationConsoleProps {
  queueState: QueueState | null;
  patients: Patient[];
  onSimulateBusy: () => void;
  onSimulateQuiet: () => void;
  onSimulateAmiFailure: () => void;
  onSimulateAmiRecovery: () => void;
  onResetPatients: () => void;
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

export function SimulationConsole({
  queueState,
  patients,
  onSimulateBusy,
  onSimulateQuiet,
  onSimulateAmiFailure,
  onSimulateAmiRecovery,
  onResetPatients,
}: SimulationConsoleProps) {
  return (
    <div className="space-y-6">
      {/* Mock Patients List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Mock Patients
              </CardTitle>
              <CardDescription>
                Simulated patient data for testing outbound calls
              </CardDescription>
            </div>
            <Badge variant="secondary">{patients.length} patients</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px]">
            <div className="space-y-2">
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
                    <div className="text-sm text-muted-foreground">
                      {patient.ai_called_before ? (
                        <Badge variant="outline" className="text-xs">AI Called</Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs">Not Called</Badge>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Queue Simulation */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Phone className="h-5 w-5" />
              Queue Simulation
            </CardTitle>
            <CardDescription>
              Simulate different queue load scenarios
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-3">
              <Button
                variant="outline"
                onClick={onSimulateQuiet}
                className="justify-start"
              >
                <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
                Quiet Queue (Allow Outbound)
              </Button>
              <Button
                variant="outline"
                onClick={onSimulateBusy}
                className="justify-start"
              >
                <XCircle className="h-4 w-4 mr-2 text-red-500" />
                Busy Queue (Block Outbound)
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Quiet: 0 calls waiting, agents available
              <br />
              Busy: 5 calls waiting, no agents available
            </p>
          </CardContent>
        </Card>

        {/* AMI Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {queueState?.ami_connected ? (
                <Wifi className="h-5 w-5 text-green-500" />
              ) : (
                <WifiOff className="h-5 w-5 text-red-500" />
              )}
              AMI Connection
            </CardTitle>
            <CardDescription>
              Simulate Asterisk Manager Interface status
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-sm text-muted-foreground">Status:</span>
              {queueState?.ami_connected ? (
                <Badge variant="success">Connected</Badge>
              ) : (
                <Badge variant="destructive">Disconnected</Badge>
              )}
            </div>
            <div className="flex flex-col gap-3">
              {queueState?.ami_connected ? (
                <Button
                  variant="outline"
                  onClick={onSimulateAmiFailure}
                  className="justify-start"
                >
                  <WifiOff className="h-4 w-4 mr-2 text-red-500" />
                  Simulate AMI Failure
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={onSimulateAmiRecovery}
                  className="justify-start"
                >
                  <Wifi className="h-4 w-4 mr-2 text-green-500" />
                  Simulate AMI Recovery
                </Button>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              When AMI is disconnected, outbound calls are blocked for safety.
            </p>
          </CardContent>
        </Card>

        {/* Patient Data */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Patient Data
            </CardTitle>
            <CardDescription>
              Manage mock patient data for testing
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              variant="outline"
              onClick={onResetPatients}
              className="justify-start"
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Reset Patient Data
            </Button>
            <p className="text-sm text-muted-foreground">
              Restores all patients to their initial state and clears call history.
            </p>
          </CardContent>
        </Card>

        {/* Current State */}
        <Card>
          <CardHeader>
            <CardTitle>Current Mock State</CardTitle>
            <CardDescription>
              Live view of simulation state
            </CardDescription>
          </CardHeader>
          <CardContent>
            {queueState ? (
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Calls Waiting:</span>
                  <span className="font-medium">{queueState.global_calls_waiting}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Oldest Wait:</span>
                  <span className="font-medium">{queueState.global_oldest_wait_seconds}s</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Agents Available:</span>
                  <span className="font-medium">
                    {queueState.global_agents_available} / {queueState.global_agents_logged_in}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Stable Polls:</span>
                  <span className="font-medium">{queueState.stable_polls_count}/3</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Outbound Allowed:</span>
                  {queueState.outbound_allowed ? (
                    <Badge variant="success">Yes</Badge>
                  ) : (
                    <Badge variant="destructive">No</Badge>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
