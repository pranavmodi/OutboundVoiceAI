"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PhoneCall, PhoneForwarded, MessageSquare } from "lucide-react";
import type { TodayKpis } from "@/types";

interface KpiBarProps {
  kpis: TodayKpis | null;
  loading?: boolean;
}

export function KpiBar({ kpis, loading }: KpiBarProps) {
  const calls = kpis?.total_calls ?? 0;
  const transferred = kpis?.transferred ?? 0;
  const voicemails = kpis?.voicemails ?? 0;
  const sms = kpis?.sms ?? 0;

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="flex items-center">
            <CardContent className="flex items-center gap-4 p-4 w-full">
              <Skeleton className="h-11 w-11 rounded-full shrink-0" />
              <div className="space-y-2 min-w-0">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-7 w-12" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="flex items-center">
        <CardContent className="flex items-center gap-4 p-4 w-full">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950/40">
            <PhoneCall className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">
              Calls Today
            </p>
            <p className="text-2xl font-semibold tabular-nums leading-tight">{calls}</p>
          </div>
        </CardContent>
      </Card>

      <Card className="flex items-center">
        <CardContent className="flex items-center gap-4 p-4 w-full">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950/40">
            <PhoneForwarded className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">
              Transferred
            </p>
            <p className="text-2xl font-semibold tabular-nums leading-tight">{transferred}</p>
          </div>
        </CardContent>
      </Card>

      <Card className="flex items-center">
        <CardContent className="flex items-center gap-4 p-4 w-full">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-50 dark:bg-amber-950/40">
            <MessageSquare className="h-5 w-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">
              VM / SMS Sent
            </p>
            <p className="text-2xl font-semibold tabular-nums leading-tight">
              {voicemails} <span className="text-muted-foreground/60 text-lg">/</span> {sms}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
