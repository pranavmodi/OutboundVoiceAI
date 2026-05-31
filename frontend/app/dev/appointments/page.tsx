"use client";

import { DevDataPanel } from "@/components/backfill/DevDataPanel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Database } from "lucide-react";

const SIM_PORT = process.env.NEXT_PUBLIC_APPOINTMENT_SIM_PORT || "3001";
const onSimPort =
  typeof window !== "undefined" && window.location.port === SIM_PORT;

export default function DevAppointmentsPage() {
  const { health } = useBackfillApi();
  const router = useRouter();
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

  return (
    <section className="container mx-auto px-4 py-6 space-y-6 max-w-6xl">
      <header className="flex items-center gap-3">
        <Database className="h-7 w-7 text-muted-foreground" />
        <span>
          <h1 className="text-2xl font-semibold">Appointment simulator</h1>
          <p className="text-sm text-muted-foreground">
            Dev only — add patients, book appointments, cancel to trigger backfill.
            {onSimPort ? (
              <> Running on port {SIM_PORT}.</>
            ) : (
              <>
                {" "}
                Also available on{" "}
                <a
                  href={`http://localhost:${SIM_PORT}/dev/appointments`}
                  className="underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  port {SIM_PORT}
                </a>
                .
              </>
            )}
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
              <Link href="/backfill" className="underline">
                Cancellation Backfill
              </Link>
              .
            </p>
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
        <DevDataPanel onCampaignCreated={() => router.push("/backfill")} />
      )}
    </section>
  );
}
