"use client";

import { useBackfillApi } from "@/hooks/useBackfillApi";
import type { CampaignDetail, Candidate, MockSmsMessage } from "@/types/backfill";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function patientLabel(c: Candidate) {
  return c.patient_name ?? `Patient #${c.patient_id}`;
}

function responseBadge(c: Candidate) {
  if (c.interested_flag) return <Badge variant="default">Interested</Badge>;
  if (c.declined_flag) return <Badge variant="secondary">Declined</Badge>;
  if (c.current_contact_status === "TextSent" || c.current_contact_status === "CallPlaced") {
    return <Badge variant="outline">Awaiting reply</Badge>;
  }
  return null;
}

type Props = {
  campaign: CampaignDetail;
  onUpdated: () => void;
};

export function MockSmsPanel({ campaign, onUpdated }: Props) {
  const { listMockSmsMessages, mockSmsReply } = useBackfillApi();
  const [messages, setMessages] = useState<MockSmsMessage[]>([]);
  const [error, setError] = useState("");
  const [loadingPatientId, setLoadingPatientId] = useState<number | null>(null);

  const contactedCandidates = useMemo(
    () =>
      campaign.candidates
        .filter(
          (c) =>
            c.current_contact_status === "TextSent" || c.current_contact_status === "CallPlaced"
        )
        .sort((a, b) => a.rank_order - b.rank_order),
    [campaign.candidates]
  );

  const messagedPatients = useMemo(() => {
    const ids = new Set<number>();
    for (const m of messages) {
      if (m.patient_id != null) ids.add(m.patient_id);
    }
    for (const c of campaign.candidates) {
      if (
        c.wave_number_first_contacted != null ||
        c.interested_flag ||
        c.declined_flag
      ) {
        ids.add(c.patient_id);
      }
    }
    return campaign.candidates
      .filter((c) => ids.has(c.patient_id))
      .sort((a, b) => a.rank_order - b.rank_order);
  }, [messages, campaign.candidates]);

  const messagesForPatient = useCallback(
    (patientId: number) =>
      messages.filter((m) => m.patient_id === patientId).sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      ),
    [messages]
  );

  const refresh = useCallback(async () => {
    const rows = await listMockSmsMessages(campaign.id);
    setMessages(rows);
  }, [campaign.id, listMockSmsMessages]);

  useEffect(() => {
    refresh().catch(() => setMessages([]));
  }, [refresh]);

  const sendReply = async (patientId: number, body: "yes" | "no") => {
    setError("");
    setLoadingPatientId(patientId);
    try {
      const result = await mockSmsReply(campaign.id, body, patientId);
      if (result.status === "unrecognized_reply") {
        setError("Use yes or no");
      } else if (result.status === "orphan_reply") {
        setError(result.message ?? "Could not match reply to campaign");
      }
      await refresh();
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mock reply failed");
    } finally {
      setLoadingPatientId(null);
    }
  };

  return (
    <Card className="border-dashed border-primary/40 bg-muted/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mock SMS (dev)</CardTitle>
        <p className="text-xs text-muted-foreground font-normal">
          One thread per patient. Reply as each person separately — no shared YES/NO buttons.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {messagedPatients.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No mock messages yet. Wait for wave SMS after cancel (within contact hours).
          </p>
        ) : (
          messagedPatients.map((candidate) => {
            const thread = messagesForPatient(candidate.patient_id);
            const canReply =
              campaign.campaign_status === "Running" &&
              (candidate.current_contact_status === "TextSent" ||
                candidate.current_contact_status === "CallPlaced");
            const busy = loadingPatientId === candidate.patient_id;

            return (
              <div
                key={candidate.id}
                className="rounded-md border border-border/60 bg-background/50 p-3 space-y-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">{patientLabel(candidate)}</span>
                  {responseBadge(candidate)}
                </div>

                {thread.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No messages in mock store yet.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {thread.map((m) => (
                      <li
                        key={m.id}
                        className={`text-sm rounded px-2 py-1.5 ${
                          m.direction === "outbound"
                            ? "bg-primary/10"
                            : "bg-muted border border-border/50"
                        }`}
                      >
                        <div className="text-xs text-muted-foreground">
                          {m.direction === "outbound" ? "Offer sent" : "Reply"} ·{" "}
                          {formatDt(m.created_at)}
                        </div>
                        <div>{m.body}</div>
                      </li>
                    ))}
                  </ul>
                )}

                {canReply ? (
                  <div className="flex gap-2 pt-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="default"
                      disabled={busy || loadingPatientId !== null}
                      onClick={() => sendReply(candidate.patient_id, "yes")}
                    >
                      {busy ? "…" : `${patientLabel(candidate)} — YES`}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busy || loadingPatientId !== null}
                      onClick={() => sendReply(candidate.patient_id, "no")}
                    >
                      {busy ? "…" : `${patientLabel(candidate)} — NO`}
                    </Button>
                  </div>
                ) : candidate.interested_flag || candidate.declined_flag ? (
                  <p className="text-xs text-muted-foreground">
                    Response recorded — no further replies for this patient on this campaign.
                  </p>
                ) : null}
              </div>
            );
          })
        )}

        {campaign.campaign_status === "Running" && contactedCandidates.length === 0 && messagedPatients.length > 0 && (
          <p className="text-xs text-muted-foreground">
            All contacted patients have responded. Start a new campaign to test again.
          </p>
        )}

        {campaign.campaign_status !== "Running" && messagedPatients.length > 0 && (
          <p className="text-xs text-muted-foreground">Campaign not running — replies disabled.</p>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
