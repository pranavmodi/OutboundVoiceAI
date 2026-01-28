"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Activity,
  Ban,
  Phone,
  PhoneOff,
  UserX,
  MonitorOff,
  Clock,
  Zap,
} from "lucide-react";
import { formatTime } from "@/lib/utils";
import type { DispatcherDecision } from "@/hooks/useWebSocket";

interface DispatcherEventsCardProps {
  events: DispatcherDecision[];
}

const decisionConfig: Record<
  string,
  { label: string; icon: typeof Activity; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }
> = {
  blocked: { label: "Blocked", icon: Ban, variant: "warning" },
  dispatched: { label: "Dispatched", icon: Phone, variant: "success" },
  call_started: { label: "Call Started", icon: Zap, variant: "success" },
  call_ended: { label: "Call Ended", icon: PhoneOff, variant: "secondary" },
  call_active: { label: "In Call", icon: Phone, variant: "default" },
  no_candidate: { label: "No Patients", icon: UserX, variant: "secondary" },
  no_frontend_connected: { label: "No Frontend", icon: MonitorOff, variant: "destructive" },
  dispatch_timeout: { label: "Timeout", icon: Clock, variant: "destructive" },
  waiting: { label: "Waiting", icon: Clock, variant: "outline" },
  started: { label: "Started", icon: Activity, variant: "success" },
  stopped: { label: "Stopped", icon: Ban, variant: "destructive" },
};

export function DispatcherEventsCard({ events }: DispatcherEventsCardProps) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Activity className="h-5 w-5" />
          Dispatcher Events
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-[300px]">
          <div className="space-y-1 p-4 pt-0">
            {events.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">
                No events yet
              </p>
            ) : (
              events.map((event, index) => {
                const config = decisionConfig[event.decision] || {
                  label: event.decision,
                  icon: Activity,
                  variant: "outline" as const,
                };
                const Icon = config.icon;

                return (
                  <div
                    key={`${event.timestamp}-${index}`}
                    className="flex items-start gap-3 rounded-md border p-3"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant={config.variant}>{config.label}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {formatTime(event.timestamp)}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1 truncate">
                        {event.detail}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
