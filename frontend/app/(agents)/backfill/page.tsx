"use client";

import { CampaignsPanel } from "@/components/backfill/CampaignsPanel";
import { SettingsPanel } from "@/components/backfill/SettingsPanel";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import { useCallback, useEffect, useState } from "react";
import { CalendarX, AlertCircle } from "lucide-react";
import type { AgentStatus } from "@/types/backfill";

export default function BackfillPage() {
  const { getAgentStatus } = useBackfillApi();
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");
  const [agentInfo, setAgentInfo] = useState<AgentStatus | null>(null);

  const refreshAgentStatus = useCallback(() => {
    getAgentStatus()
      .then((res) => {
        if (res && res.status === "ok") {
          setStatus("ok");
          setAgentInfo(res);
        } else {
          setStatus("down");
          setAgentInfo(null);
        }
      })
      .catch(() => {
        setStatus("down");
        setAgentInfo(null);
      });
  }, [getAgentStatus]);

  useEffect(() => {
    let cancelled = false;
    getAgentStatus()
      .then((res) => {
        if (cancelled) return;
        if (res && res.status === "ok") {
          setStatus("ok");
          setAgentInfo(res);
        } else {
          setStatus("down");
          setAgentInfo(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("down");
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
            View and manage backfill campaigns.
          </p>
        </span>
      </header>

      {status === "down" && (
        <Card className="border-destructive/40">
          <CardContent className="py-4">
            <p className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 text-red-600" />
              Backfill backend is not reachable. Start{" "}
              <code className="bg-muted px-1 rounded">backfill-backend/run.sh</code>
            </p>
          </CardContent>
        </Card>
      )}

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
            <CampaignsPanel mockSmsEnabled={agentInfo?.mock_sms_enabled ?? false} />
          </TabsContent>
          <TabsContent value="settings">
            <SettingsPanel onSmsModeChanged={refreshAgentStatus} />
          </TabsContent>
        </Tabs>
      )}
    </section>
  );
}
