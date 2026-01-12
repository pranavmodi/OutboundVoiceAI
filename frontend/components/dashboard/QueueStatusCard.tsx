"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Users,
  Phone,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { QueueState } from "@/types";

interface QueueStatusCardProps {
  queueState: QueueState | null;
  onSimulateBusy: () => void;
  onSimulateQuiet: () => void;
  onSimulateAmiFailure: () => void;
  onSimulateAmiRecovery: () => void;
}

export function QueueStatusCard({
  queueState,
  onSimulateBusy,
  onSimulateQuiet,
  onSimulateAmiFailure,
  onSimulateAmiRecovery,
}: QueueStatusCardProps) {
  if (!queueState) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Phone className="h-5 w-5" />
            Queue Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Phone className="h-5 w-5" />
            Queue Status
          </CardTitle>
          <div className="flex items-center gap-2">
            {queueState.ami_connected ? (
              <Badge variant="success" className="flex items-center gap-1">
                <Wifi className="h-3 w-3" />
                AMI Connected
              </Badge>
            ) : (
              <Badge variant="destructive" className="flex items-center gap-1">
                <WifiOff className="h-3 w-3" />
                AMI Disconnected
              </Badge>
            )}
            <Badge variant="outline">Mock Mode</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Main Metrics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Users className="h-4 w-4" />
              Agents Available
            </div>
            <p className="text-2xl font-bold">{queueState.global_agents_available}</p>
            <p className="text-xs text-muted-foreground">
              of {queueState.global_agents_logged_in} logged in
            </p>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Phone className="h-4 w-4" />
              Calls Waiting
            </div>
            <p className="text-2xl font-bold">{queueState.global_calls_waiting}</p>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              Oldest Wait
            </div>
            <p className="text-2xl font-bold">{queueState.global_oldest_wait_seconds}s</p>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              Stable Polls
            </div>
            <p className="text-2xl font-bold">{queueState.stable_polls_count}/3</p>
          </div>
        </div>

        <Separator />

        {/* Outbound Status */}
        <div className="flex items-center justify-between">
          <span className="font-medium">Outbound Allowed</span>
          {queueState.outbound_allowed ? (
            <Badge variant="success" className="flex items-center gap-1">
              <CheckCircle className="h-3 w-3" />
              Yes
            </Badge>
          ) : (
            <Badge variant="destructive" className="flex items-center gap-1">
              <XCircle className="h-3 w-3" />
              No
            </Badge>
          )}
        </div>

        {!queueState.outbound_allowed && (
          <div className="flex items-start gap-2 rounded-md bg-yellow-50 p-3 text-sm text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              {!queueState.ami_connected
                ? "AMI connection lost. Outbound disabled for safety."
                : queueState.global_agents_available === 0
                ? "No agents available to handle transfers."
                : queueState.global_calls_waiting > 1
                ? "Queue has calls waiting. Outbound paused."
                : queueState.stable_polls_count < 3
                ? `Waiting for stable conditions (${queueState.stable_polls_count}/3 polls).`
                : "Conditions not met for outbound calls."}
            </div>
          </div>
        )}

        <Separator />

        {/* Individual Queues */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-muted-foreground">Individual Queues</h4>
          <div className="space-y-2">
            {queueState.queues.map((queue) => (
              <div
                key={queue.queue_name}
                className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm"
              >
                <span className="font-medium">{queue.queue_name}</span>
                <div className="flex items-center gap-4 text-muted-foreground">
                  <span>{queue.agents_available} agents</span>
                  <span>{queue.calls_waiting} waiting</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Simulation Controls */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-muted-foreground">Simulate Scenarios</h4>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={onSimulateQuiet}>
              Quiet Queue
            </Button>
            <Button variant="outline" size="sm" onClick={onSimulateBusy}>
              Busy Queue
            </Button>
            {queueState.ami_connected ? (
              <Button variant="outline" size="sm" onClick={onSimulateAmiFailure}>
                AMI Failure
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={onSimulateAmiRecovery}>
                AMI Recovery
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
