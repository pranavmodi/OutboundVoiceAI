"use client";

import { CampaignsPanel } from "@/components/backfill/CampaignsPanel";
import { SettingsPanel } from "@/components/backfill/SettingsPanel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import { useEffect, useState } from "react";
import { CalendarX, AlertCircle, CheckCircle2 } from "lucide-react";

export default function BackfillPage() {
  const { getAgentStatus } = useBackfillApi();
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");
  const [agentEnabled, setAgentEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAgentStatus()
      .then((res) => {
        if (cancelled) return;
        if (res && res.status === "ok") {
          setStatus("ok");
          setAgentEnabled(res.enabled);
        } else {
          setStatus("down");
          setAgentEnabled(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("down");
          setAgentEnabled(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [getAgentStatus]);

  return (
    <section className="container mx-auto px-4 py-6 space-y-6 max-w-6xl">
      <header className="flex items-center gap-3">
        <CalendarX className="h-7 w-7 text-primary" />
        <span>
          <h1 className="text-2xl font-semibold">Cancellation Backfill</h1>
          <p className="text-sm text-muted-foreground">
            View and manage backfill campaigns. Appointment simulator:{" "}
            <a href="/dev/appointments" className="underline">
              /dev/appointments
            </a>{" "}
            (or{" "}
            <a
              href={
                process.env.NEXT_PUBLIC_APPOINTMENT_SIM_URL ||
                "http://localhost:3001/dev/appointments"
              }
              className="underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              :3001
            </a>
            ).
          </p>
        </span>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backend status</CardTitle>
        </CardHeader>
        <CardContent>
          {status === "loading" && (
            <p className="text-sm text-muted-foreground">Checking backfill-backend...</p>
          )}
          {status === "ok" && (
            <div className="space-y-1 text-sm">
              <p className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                Backfill backend is reachable.
              </p>
              {agentEnabled !== null && (
                <p className="text-muted-foreground">
                  Agent: <strong>{agentEnabled ? "Enabled" : "Disabled"}</strong> (new campaigns{" "}
                  {agentEnabled ? "allowed" : "blocked"})
                </p>
              )}
            </div>
          )}
          {status === "down" && (
            <p className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 text-red-600" />
              Start <code className="bg-muted px-1 rounded">backfill-backend/run.sh</code>
            </p>
          )}
        </CardContent>
      </Card>

      {status === "ok" && (
        <Tabs defaultValue="campaigns">
          <TabsList>
            <TabsTrigger value="campaigns">Campaigns</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
            <TabsTrigger value="reports" disabled>
              Reports (M2)
            </TabsTrigger>
          </TabsList>
          <TabsContent value="campaigns">
            <CampaignsPanel />
          </TabsContent>
          <TabsContent value="settings">
            <SettingsPanel />
          </TabsContent>
        </Tabs>
      )}
    </section>
  );
}
