"use client";

import { DevDataPanel } from "@/components/DevDataPanel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import { AlertCircle, CheckCircle2, Database } from "lucide-react";
import { useEffect, useState } from "react";

const BACKFILL_UI_URL =
  process.env.NEXT_PUBLIC_BACKFILL_UI_URL || "http://localhost:3000";

export default function DevAppointmentsPage() {
  const { health } = useBackfillApi();
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");

  useEffect(() => {
    let cancelled = false;
    health()
      .then((res) => {
        if (!cancelled) setStatus(res ? "ok" : "down");
      })
      .catch(() => {
        if (!cancelled) setStatus("down");
      });
    return () => {
      cancelled = true;
    };
  }, [health]);

  const openCampaigns = () => {
    window.open(`${BACKFILL_UI_URL}/backfill`, "_blank", "noopener,noreferrer");
  };

  return (
    <section className="container mx-auto px-4 py-6 space-y-6 max-w-6xl">
      <header className="flex items-center gap-3">
        <Database className="h-7 w-7 text-muted-foreground" />
        <span>
          <h1 className="text-2xl font-semibold">Appointment simulator</h1>
          <p className="text-sm text-muted-foreground">
            Dev only (port 3001) — add patients, book appointments, cancel to trigger backfill.
            Operator UI runs on{" "}
            <a href={BACKFILL_UI_URL} className="underline">
              {BACKFILL_UI_URL}
            </a>
            .
          </p>
        </span>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backend</CardTitle>
        </CardHeader>
        <CardContent>
          {status === "loading" && <p className="text-sm text-muted-foreground">Checking...</p>}
          {status === "ok" && (
            <p className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              Connected. After cancel, view campaigns on{" "}
              <button type="button" className="underline" onClick={openCampaigns}>
                Cancellation Backfill
              </button>
              .
            </p>
          )}
          {status === "down" && (
            <p className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 text-red-600" />
              Start backfill-backend/run.sh
            </p>
          )}
        </CardContent>
      </Card>

      {status === "ok" && <DevDataPanel onCampaignCreated={openCampaigns} />}
    </section>
  );
}
