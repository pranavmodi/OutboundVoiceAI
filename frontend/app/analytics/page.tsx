"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { TimePerformance, DayStats, HourStats } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, BarChart3, Clock, Calendar } from "lucide-react";
import Link from "next/link";

function rateColor(rate: number, metric: "transfer" | "no_answer" | "voicemail"): string {
  if (metric === "transfer") {
    if (rate >= 50) return "bg-emerald-600 text-white";
    if (rate >= 30) return "bg-emerald-400 text-white";
    if (rate >= 15) return "bg-emerald-200 text-emerald-900";
    if (rate > 0) return "bg-emerald-50 text-emerald-800";
    return "bg-gray-50 text-gray-400";
  }
  if (metric === "no_answer") {
    if (rate >= 60) return "bg-red-600 text-white";
    if (rate >= 40) return "bg-red-400 text-white";
    if (rate >= 20) return "bg-red-200 text-red-900";
    if (rate > 0) return "bg-red-50 text-red-800";
    return "bg-gray-50 text-gray-400";
  }
  // voicemail
  if (rate >= 50) return "bg-amber-600 text-white";
  if (rate >= 30) return "bg-amber-400 text-white";
  if (rate >= 15) return "bg-amber-200 text-amber-900";
  if (rate > 0) return "bg-amber-50 text-amber-800";
  return "bg-gray-50 text-gray-400";
}

function formatMs(ms: number | null | undefined): string {
  if (typeof ms !== "number") return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function ttfsColor(ms: number | null | undefined): string {
  if (typeof ms !== "number") return "text-muted-foreground";
  if (ms < 2000) return "text-emerald-700";
  if (ms < 4000) return "text-amber-700";
  return "text-red-700";
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card>
      <CardContent className="pt-6 pb-4 text-center">
        <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">{label}</p>
        <p className="text-3xl font-bold">{value}</p>
        <p className="text-sm text-muted-foreground mt-1">{sub}</p>
      </CardContent>
    </Card>
  );
}

function StatsTable<T extends DayStats | HourStats>({
  rows,
  labelKey,
  title,
  icon,
}: {
  rows: T[];
  labelKey: keyof T;
  title: string;
  icon: React.ReactNode;
}) {
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-base">{icon} {title}</CardTitle></CardHeader>
        <CardContent><p className="text-muted-foreground text-sm">No data available.</p></CardContent>
      </Card>
    );
  }

  // Find best transfer rate row
  const maxTransfer = Math.max(...rows.map((r) => r.transfer_rate));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">{icon} {title}</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4 font-medium text-muted-foreground"></th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Total</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-center">Transfer %</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-center">No Answer %</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-center">Voicemail %</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Avg TTFS</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-center">TTFS &lt;2s</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Transferred</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">No Answer</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Voicemail</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Callback</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Hung Up</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Wrong #</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Error</th>
              <th className="py-2 px-3 font-medium text-muted-foreground text-right">Disconn.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isBest = row.transfer_rate === maxTransfer && maxTransfer > 0;
              return (
                <tr
                  key={i}
                  className={`border-b last:border-0 ${isBest ? "bg-emerald-50/50" : ""}`}
                >
                  <td className="py-2 pr-4 font-medium whitespace-nowrap">
                    {String(row[labelKey])}
                    {isBest && <span className="ml-2 text-xs text-emerald-600 font-semibold">BEST</span>}
                  </td>
                  <td className="py-2 px-3 text-right font-semibold">{row.total}</td>
                  <td className="py-2 px-3 text-center">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${rateColor(row.transfer_rate, "transfer")}`}>
                      {row.transfer_rate}%
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${rateColor(row.no_answer_rate, "no_answer")}`}>
                      {row.no_answer_rate}%
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${rateColor(row.voicemail_rate, "voicemail")}`}>
                      {row.voicemail_rate}%
                    </span>
                  </td>
                  <td className={`py-2 px-3 text-right font-mono font-semibold ${ttfsColor(row.avg_ttfs_ms)}`}>{formatMs(row.avg_ttfs_ms)}</td>
                  <td className="py-2 px-3 text-center">
                    <span className="inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-800">
                      {row.ttfs_count ? `${row.fast_ttfs_rate}%` : "--"}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.transferred}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.no_answer}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.voicemail}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.callback}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.hung_up}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.wrong_number}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.technical_error}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{row.disconnected_number}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const api = useApi();
  const [data, setData] = useState<TimePerformance | null>(null);
  const [days, setDays] = useState(90);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getTimePerformance(days).then((result) => {
      if (!cancelled) {
        setData(result);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [days, api]);

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <div>
              <h1 className="text-xl font-semibold flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Reach and First Speech Performance
              </h1>
              <p className="text-sm text-muted-foreground">
                Best day/time to reach patients plus time to first AI speech ({data?.timezone || "America/Los_Angeles"})
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {[1, 7, 30, 60, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  days === d
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Card key={i}>
                  <CardContent className="pt-6 pb-4 text-center">
                    <Skeleton className="h-3 w-20 mx-auto mb-2" />
                    <Skeleton className="h-8 w-16 mx-auto mb-1" />
                    <Skeleton className="h-3 w-28 mx-auto" />
                  </CardContent>
                </Card>
              ))}
            </div>
            <Card>
              <CardHeader><Skeleton className="h-5 w-40" /></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[0, 1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="flex gap-3">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-4 w-12" />
                      <Skeleton className="h-4 w-16 rounded-full" />
                      <Skeleton className="h-4 w-16 rounded-full" />
                      <Skeleton className="h-4 w-16 rounded-full" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : !data || data.total_calls === 0 ? (
          <Card>
            <CardContent className="py-20 text-center text-muted-foreground">
              No call data found for the last {days} days.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {/* KPI row */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <KpiCard
                label="Total Calls"
                value={data.total_calls.toLocaleString()}
                sub={`Last ${data.days} days`}
              />
              <KpiCard
                label="Transfer Rate"
                value={`${data.overall_transfer_rate}%`}
                sub="Transferred to scheduling"
              />
              <KpiCard
                label="No Answer Rate"
                value={`${data.overall_no_answer_rate}%`}
                sub="Did not pick up"
              />
              <KpiCard
                label="Voicemail Rate"
                value={`${data.overall_voicemail_rate}%`}
                sub="Reached voicemail"
              />
              <KpiCard
                label="Avg TTFS"
                value={formatMs(data.overall_avg_ttfs_ms)}
                sub={`${data.ttfs_count.toLocaleString()} calls with timing`}
              />
              <KpiCard
                label="TTFS <2s"
                value={data.ttfs_count ? `${data.overall_fast_ttfs_rate}%` : "--"}
                sub="First AI audio under target"
              />
            </div>

            {/* By day of week */}
            <StatsTable
              rows={data.by_day}
              labelKey="day_name"
              title="By Day of Week"
              icon={<Calendar className="h-4 w-4" />}
            />

            {/* By hour of day */}
            <StatsTable
              rows={data.by_hour}
              labelKey="label"
              title="By Hour of Day"
              icon={<Clock className="h-4 w-4" />}
            />
          </div>
        )}
      </div>
    </div>
  );
}
