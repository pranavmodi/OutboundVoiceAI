"use client";

import { MockSmsPanel } from "@/components/backfill/MockSmsPanel";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import type { Campaign, CampaignDetail, CampaignListParams, Facility, TimelineEntry } from "@/types/backfill";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusBadgeVariant(status: string): "default" | "success" | "secondary" | "destructive" {
  if (status === "Running") return "default";
  if (status === "Filled") return "success";
  if (status === "ClosedSystemError") return "destructive";
  return "secondary";
}

function responseLabel(candidate: CampaignDetail["candidates"][number]) {
  if (candidate.won_slot_flag) return "Won";
  if (candidate.lost_slot_flag) return "Lost";
  if (candidate.interested_flag) return "Interested";
  if (candidate.declined_flag) return "Declined";
  if (candidate.no_response_flag) return "No response";
  return candidate.current_contact_status ?? "—";
}

const STATUS_OPTIONS = [
  "Running",
  "Pending",
  "Filled",
  "ClosedNoCandidates",
  "ClosedManually",
  "ClosedExhausted",
  "ClosedMaxWavesReached",
  "ClosedSlotNoLongerAvailable",
  "ClosedSystemError",
];

type Props = {
  refreshKey?: number;
  mockSmsEnabled?: boolean;
};

export function CampaignsPanel({ refreshKey = 0, mockSmsEnabled = false }: Props) {
  const { listCampaigns, listFacilities, getCampaign, getCampaignTimeline, stopCampaign } =
    useBackfillApi();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [total, setTotal] = useState(0);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [selected, setSelected] = useState<CampaignDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [error, setError] = useState("");
  const [stopping, setStopping] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [startedFrom, setStartedFrom] = useState("");
  const [startedTo, setStartedTo] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [cptCode, setCptCode] = useState("");
  const [filledFilter, setFilledFilter] = useState<"" | "true" | "false">("");
  const [sort, setSort] = useState("started_at_desc");

  const buildParams = useCallback((): CampaignListParams => {
    const params: CampaignListParams = { sort, page: 1, page_size: 50 };
    if (startedFrom) params.started_from = new Date(startedFrom).toISOString();
    if (startedTo) params.started_to = new Date(startedTo).toISOString();
    if (facilityId) params.facility_id = facilityId;
    if (statusFilter) params.status = statusFilter;
    if (cptCode.trim()) params.cpt_code = cptCode.trim();
    if (filledFilter === "true") params.filled = true;
    if (filledFilter === "false") params.filled = false;
    return params;
  }, [startedFrom, startedTo, facilityId, statusFilter, cptCode, filledFilter, sort]);

  const loadList = useCallback(async () => {
    const res = await listCampaigns(buildParams());
    setCampaigns(res.items);
    setTotal(res.total);
    return res.items;
  }, [listCampaigns, buildParams]);

  const openDetail = useCallback(
    async (id: number) => {
      setError("");
      const [detail, entries] = await Promise.all([getCampaign(id), getCampaignTimeline(id)]);
      setSelected(detail);
      setTimeline(entries);
    },
    [getCampaign, getCampaignTimeline]
  );

  const load = useCallback(async () => {
    setError("");
    try {
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaigns");
    }
  }, [loadList]);

  useEffect(() => {
    listFacilities()
      .then(setFacilities)
      .catch(() => setFacilities([]));
  }, [listFacilities]);

  useEffect(() => {
    load();
    setSelected(null);
    setTimeline([]);
  }, [load, refreshKey]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setError("");
    try {
      await loadList();
      if (selected) await openDetail(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh");
      if (selected) {
        setSelected(null);
        setTimeline([]);
      }
    } finally {
      setRefreshing(false);
    }
  }, [loadList, openDetail, selected]);

  const applyFilters = () => {
    setSelected(null);
    setTimeline([]);
    load();
  };

  const selectCampaign = async (id: number) => {
    setError("");
    try {
      await openDetail(id);
    } catch (e) {
      setSelected(null);
      setTimeline([]);
      setError(e instanceof Error ? e.message : "Failed to load campaign");
    }
  };

  const handleStop = async (id: number) => {
    setStopping(true);
    setError("");
    try {
      const detail = await stopCampaign(id);
      setSelected(detail);
      setTimeline(await getCampaignTimeline(id));
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop campaign");
    } finally {
      setStopping(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <Label htmlFor="started-from">Started from</Label>
            <Input
              id="started-from"
              type="datetime-local"
              value={startedFrom}
              onChange={(e) => setStartedFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="started-to">Started to</Label>
            <Input
              id="started-to"
              type="datetime-local"
              value={startedTo}
              onChange={(e) => setStartedTo(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Facility</Label>
            <Select value={facilityId || "all"} onValueChange={(v) => setFacilityId(v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All facilities" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All facilities</SelectItem>
                {facilities.map((f) => (
                  <SelectItem key={f.id} value={String(f.id)}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Status</Label>
            <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {STATUS_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cpt-filter">CPT code</Label>
            <Input id="cpt-filter" value={cptCode} onChange={(e) => setCptCode(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Filled</Label>
            <Select
              value={filledFilter || "all"}
              onValueChange={(v) => setFilledFilter(v === "all" ? "" : (v as "true" | "false"))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="true">Filled only</SelectItem>
                <SelectItem value="false">Unfilled only</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Sort</Label>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="started_at_desc">Started (newest)</SelectItem>
                <SelectItem value="started_at_asc">Started (oldest)</SelectItem>
                <SelectItem value="open_slot_start_at_desc">Slot (latest)</SelectItem>
                <SelectItem value="open_slot_start_at_asc">Slot (earliest)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end gap-2 sm:col-span-2">
            <Button type="button" onClick={applyFilters}>
              Apply filters
            </Button>
            <Button type="button" variant="outline" disabled={refreshing} onClick={handleRefresh}>
              {refreshing ? "Refreshing..." : "Refresh"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Campaigns ({total})</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {campaigns.length === 0 ? (
              <p className="text-sm text-muted-foreground">No campaigns match filters.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-2">ID</th>
                    <th className="py-2 pr-2">Canceled by</th>
                    <th className="py-2 pr-2">Facility</th>
                    <th className="py-2 pr-2">CPT</th>
                    <th className="py-2 pr-2">Slot</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">Started</th>
                    <th className="py-2 pr-2">Ended</th>
                    <th className="py-2 pr-2">Filled by</th>
                    <th className="py-2 pr-2">Close reason</th>
                    <th className="py-2 pr-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c) => (
                    <tr key={c.id} className="border-b border-border/40">
                      <td className="py-2 pr-2">
                        <button
                          type="button"
                          className="text-primary underline"
                          onClick={() => selectCampaign(c.id)}
                        >
                          {c.id}
                        </button>
                      </td>
                      <td className="py-2 pr-2">
                        {c.cancelled_patient_name ?? `Patient #${c.cancelled_patient_id}`}
                      </td>
                      <td className="py-2 pr-2">{c.facility_name}</td>
                      <td className="py-2 pr-2">{c.cpt_code}</td>
                      <td className="py-2 pr-2 whitespace-nowrap">{formatDt(c.open_slot_start_at)}</td>
                      <td className="py-2 pr-2">
                        <Badge variant={statusBadgeVariant(c.campaign_status)}>{c.campaign_status}</Badge>
                      </td>
                      <td className="py-2 pr-2 whitespace-nowrap">{formatDt(c.started_at)}</td>
                      <td className="py-2 pr-2 whitespace-nowrap">
                        {c.ended_at ? formatDt(c.ended_at) : "—"}
                      </td>
                      <td className="py-2 pr-2">
                        {c.filled_by_patient_name ??
                          (c.filled_by_patient_id ? `Patient #${c.filled_by_patient_id}` : "—")}
                      </td>
                      <td className="py-2 pr-2">{c.closed_reason ?? "—"}</td>
                      <td className="py-2 pr-2 space-x-1">
                        <Button type="button" size="sm" variant="outline" onClick={() => selectCampaign(c.id)}>
                          View
                        </Button>
                        {c.campaign_status === "Running" && (
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            disabled={stopping}
                            onClick={() => handleStop(c.id)}
                          >
                            Stop
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Campaign detail</CardTitle>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <p className="text-sm text-muted-foreground">Select a campaign to see detail.</p>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant={statusBadgeVariant(selected.campaign_status)}>
                    {selected.campaign_status}
                  </Badge>
                  {selected.campaign_status === "Running" && (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      disabled={stopping}
                      onClick={() => handleStop(selected.id)}
                    >
                      {stopping ? "Stopping..." : "Stop"}
                    </Button>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  Canceled by:{" "}
                  {selected.cancelled_patient_name ?? `Patient #${selected.cancelled_patient_id}`} ·
                  Facility: {selected.facility_name} · CPT: {selected.cpt_code}
                </p>
                <p className="text-sm text-muted-foreground">
                  Slot: {formatDt(selected.open_slot_start_at)} · Started: {formatDt(selected.started_at)}
                  {selected.ended_at && ` · Ended: ${formatDt(selected.ended_at)}`}
                </p>
                {selected.filled_by_patient_name && (
                  <p className="text-sm">
                    Filled by: {selected.filled_by_patient_name}
                    {selected.filled_by_appointment_id != null &&
                      ` (appt #${selected.filled_by_appointment_id})`}
                  </p>
                )}
                {selected.closed_reason && (
                  <p className="text-sm">
                    <strong>Close reason:</strong> {selected.closed_reason}
                  </p>
                )}

                {mockSmsEnabled && (
                  <MockSmsPanel
                    campaign={selected}
                    onUpdated={() => openDetail(selected.id)}
                  />
                )}

                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-1">Rank</th>
                      <th className="py-1">Patient</th>
                      <th className="py-1">IDs</th>
                      <th className="py-1">Appt date</th>
                      <th className="py-1">Status</th>
                      <th className="py-1">Wave</th>
                      <th className="py-1">Last contact</th>
                      <th className="py-1">Response</th>
                      <th className="py-1">Response time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.candidates.map((cand) => (
                      <tr
                        key={cand.id}
                        className={
                          cand.eligibility_status !== "Eligible"
                            ? "opacity-50 border-b border-border/40"
                            : "border-b border-border/40"
                        }
                        >
                        <td className="py-1">{cand.rank_order < 9000 ? cand.rank_order : "—"}</td>
                        <td className="py-1">{cand.patient_name ?? `Patient #${cand.patient_id}`}</td>
                        <td className="py-1 text-xs text-muted-foreground">
                          P{cand.patient_id} / A{cand.appointment_id}
                        </td>
                        <td className="py-1">{formatDt(cand.scheduled_appointment_at)}</td>
                        <td className="py-1">
                          {cand.eligibility_status}
                          {cand.exclusion_reason && (
                            <span className="block text-xs text-muted-foreground">{cand.exclusion_reason}</span>
                          )}
                        </td>
                        <td className="py-1">{cand.wave_number_first_contacted ?? "—"}</td>
                        <td className="py-1">
                          {cand.last_contacted_at ? formatDt(cand.last_contacted_at) : "—"}
                        </td>
                        <td className="py-1">{responseLabel(cand)}</td>
                        <td className="py-1">{cand.response_at ? formatDt(cand.response_at) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="pt-2">
                  <p className="text-sm font-medium mb-2">Outreach timeline</p>
                  {timeline.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No events logged yet.</p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="py-1 pr-2">Time</th>
                          <th className="py-1 pr-2">Event</th>
                          <th className="py-1 pr-2">Patient</th>
                          <th className="py-1 pr-2">Channel</th>
                          <th className="py-1 pr-2">Wave</th>
                          <th className="py-1 pr-2">Outcome</th>
                          <th className="py-1 pr-2">Provider ID</th>
                        </tr>
                      </thead>
                      <tbody>
                        {timeline.map((row) => (
                          <tr key={row.id} className="border-b border-border/40">
                            <td className="py-1 pr-2 whitespace-nowrap">{formatDt(row.attempted_at)}</td>
                            <td className="py-1 pr-2">{row.action_type}</td>
                            <td className="py-1 pr-2">
                              {row.patient_name ??
                                (row.patient_id ? `Patient #${row.patient_id}` : "—")}
                            </td>
                            <td className="py-1 pr-2">{row.channel}</td>
                            <td className="py-1 pr-2">{row.wave_number ?? "—"}</td>
                            <td className="py-1 pr-2">{row.outcome ?? "—"}</td>
                            <td className="py-1 pr-2">{row.provider_message_id ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
