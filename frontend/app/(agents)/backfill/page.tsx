"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import { useEffect, useState } from "react";
import { CalendarX, AlertCircle, CheckCircle2 } from "lucide-react";

export default function BackfillPage() {
  const { health } = useBackfillApi();
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");

  useEffect(() => {
    let cancelled = false;
    health()
      .then((res) => {
        if (cancelled) return;
        setStatus(res ? "ok" : "down");
      })
      .catch(() => {
        if (!cancelled) setStatus("down");
      });
    return () => {
      cancelled = true;
    };
  }, [health]);

  return (
    <div className="container mx-auto px-4 py-6 space-y-6 max-w-5xl">
      <div className="flex items-center gap-3">
        <CalendarX className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold">Cancellation Backfill</h1>
          <p className="text-sm text-muted-foreground">
            Fills canceled appointment slots by reaching out to already-scheduled patients.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backend status</CardTitle>
        </CardHeader>
        <CardContent>
          {status === "loading" && (
            <p className="text-sm text-muted-foreground">Checking backfill-backend...</p>
          )}
          {status === "ok" && (
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span>Backfill backend is reachable.</span>
            </div>
          )}
          {status === "down" && (
            <div className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 text-red-600" />
              <span>
                Backfill backend not reachable. Start it via{" "}
                <code className="bg-muted px-1 rounded">backfill-backend/run.sh</code> and ensure{" "}
                <code className="bg-muted px-1 rounded">NEXT_PUBLIC_BACKFILL_API_URL</code> is set.
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Campaigns</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Campaign list, detail, settings, and reports land here as the spec is implemented.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
