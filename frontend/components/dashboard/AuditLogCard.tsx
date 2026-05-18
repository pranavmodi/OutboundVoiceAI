"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FileText,
  RefreshCw,
  Download,
  Search,
  X,
} from "lucide-react";
import { formatTime, formatDate } from "@/lib/utils";
import { useApi } from "@/hooks/useApi";
import type { AuditEvent } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const EVENT_TYPE_COLORS: Record<string, string> = {
  radflow: "text-purple-700 bg-purple-50 border-purple-200",
  hl7: "text-red-700 bg-red-50 border-red-200",
  sms: "text-blue-700 bg-blue-50 border-blue-200",
  email: "text-amber-700 bg-amber-50 border-amber-200",
  slack: "text-emerald-700 bg-emerald-50 border-emerald-200",
};

const STATUS_VARIANT: Record<string, "success" | "destructive" | "secondary"> = {
  success: "success",
  failed: "destructive",
  skipped: "secondary",
};

const PAGE_SIZE = 50;

export function AuditLogCard() {
  const api = useApi();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const fetchEvents = useCallback(async (offset = 0, append = false) => {
    setLoading(true);
    const { events: e, total: t } = await api.getAuditLog({
      limit: PAGE_SIZE,
      offset,
      event_type: eventType,
      status: statusFilter,
      search: search.trim() || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    });
    if (append) {
      setEvents((prev) => [...prev, ...e]);
    } else {
      setEvents(e);
    }
    setTotal(t);
    setLoading(false);
  }, [api, eventType, statusFilter, search, startDate, endDate]);

  useEffect(() => {
    const t = setTimeout(() => fetchEvents(0), 300);
    return () => clearTimeout(t);
  }, [fetchEvents]);

  const handleExportCsv = () => {
    const params = new URLSearchParams();
    params.set("format", "csv");
    if (eventType !== "all") params.set("event_type", eventType);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (search.trim()) params.set("search", search.trim());
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    window.open(`${API_BASE}/api/audit?${params.toString()}`, "_blank");
  };

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileText className="h-5 w-5" />
            Audit Log
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground tabular-nums">
              {events.length} of {total} events
            </span>
            <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={handleExportCsv}>
              <Download className="h-3 w-3" />
              Export CSV
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => fetchEvents(0)}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="relative pt-2">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 mt-1 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <Input
            type="text"
            placeholder="Search by patient, order ID, or summary..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 pr-8 text-xs"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 mt-1 text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 pt-2 flex-wrap">
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="h-7 rounded-md border bg-background px-2 text-xs cursor-pointer"
          >
            <option value="all">All Types</option>
            <option value="radflow">RadFlow</option>
            <option value="hl7">HL7</option>
            <option value="sms">SMS</option>
            <option value="email">Email</option>
            <option value="slack">Slack</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-7 rounded-md border bg-background px-2 text-xs cursor-pointer"
          >
            <option value="all">All Statuses</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
            <option value="skipped">Skipped</option>
          </select>
          <Input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-7 w-[130px] text-xs"
          />
          <Input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-7 w-[130px] text-xs"
          />
          {(startDate || endDate) && (
            <button
              onClick={() => { setStartDate(""); setEndDate(""); }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear dates
            </button>
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-[600px]">
          <div className="px-6 pb-6 pt-2">
            {loading && events.length === 0 ? (
              <div className="space-y-2">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex items-center gap-3 py-2 border-b last:border-0">
                    <Skeleton className="h-5 w-16 rounded-full" />
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-20 ml-auto" />
                  </div>
                ))}
              </div>
            ) : events.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <FileText className="h-12 w-12 mb-3 opacity-10" />
                <p className="text-sm font-medium">No audit events</p>
                <p className="text-xs mt-1">External API calls will be logged here</p>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b text-left">
                    <th className="py-2 pr-2 font-medium text-muted-foreground whitespace-nowrap">Time</th>
                    <th className="py-2 px-2 font-medium text-muted-foreground">Patient</th>
                    <th className="py-2 px-2 font-medium text-muted-foreground">Type</th>
                    <th className="py-2 px-2 font-medium text-muted-foreground">Status</th>
                    <th className="py-2 px-2 font-medium text-muted-foreground">Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} className="border-b last:border-0 hover:bg-muted/30 align-top">
                      <td className="py-2.5 pr-2 whitespace-nowrap tabular-nums text-muted-foreground">
                        <div>{e.created_at ? formatDate(e.created_at) : "—"}</div>
                        <div>{e.created_at ? formatTime(e.created_at) : ""}</div>
                      </td>
                      <td className="py-2.5 px-2">
                        <div className="font-medium">{e.patient_name || "—"}</div>
                        <div className="text-muted-foreground font-mono text-[10px]">{e.patient_id || ""}</div>
                        {e.order_id && (
                          <div className="text-muted-foreground text-[10px]">Order: {e.order_id}</div>
                        )}
                      </td>
                      <td className="py-2.5 px-2">
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${EVENT_TYPE_COLORS[e.event_type] || ""}`}>
                          {e.event_type}
                        </Badge>
                        <div className="text-[10px] text-muted-foreground mt-0.5">{e.action}</div>
                      </td>
                      <td className="py-2.5 px-2">
                        <Badge variant={STATUS_VARIANT[e.status] || "secondary"} className="text-[10px] px-1.5 py-0">
                          {e.status}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-2">
                        <div className="break-words whitespace-pre-wrap max-w-[400px]">
                          {e.request_summary}
                        </div>
                        {e.error_message && (
                          <div className="text-destructive break-words whitespace-pre-wrap mt-0.5 max-w-[400px]">
                            {e.error_message}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {events.length < total && (
              <div className="flex justify-center pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => fetchEvents(events.length, true)}
                  disabled={loading}
                >
                  {loading ? "Loading..." : `Load more (${total - events.length} remaining)`}
                </Button>
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
