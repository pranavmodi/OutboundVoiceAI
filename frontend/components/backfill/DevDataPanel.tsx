"use client";

import { useAppointmentSimApi } from "@/hooks/useAppointmentSimApi";
import { useBackfillApi } from "@/hooks/useBackfillApi";
import { defaultSimulatorFacilityId } from "@/lib/simulatorDefaults";
import type { Appointment, Facility, Patient } from "@/types/backfill";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Minus } from "lucide-react";

function formatDt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

type Props = { onCampaignCreated?: () => void };

export function DevDataPanel({ onCampaignCreated }: Props) {
  const sim = useAppointmentSimApi();
  const backfill = useBackfillApi();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [facilityName, setFacilityName] = useState("");
  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [patientId, setPatientId] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [cptCode, setCptCode] = useState("MRI_BRAIN");
  const [scheduledAt, setScheduledAt] = useState("");

  const refresh = useCallback(async () => {
    const [f, p, a] = await Promise.all([
      sim.listFacilities(),
      sim.listPatients(),
      sim.listAppointments(),
    ]);
    setFacilities(f);
    setPatients(p);
    setAppointments(a);
    if (f.length) setFacilityId((prev) => prev || defaultSimulatorFacilityId(f));
    if (p.length) setPatientId((prev) => prev || String(p[0].id));
  }, [sim]);

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [refresh]);

  const run = async (fn: () => Promise<void>) => {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const selectCls = "flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Quick start</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Load demo data, then cancel a scheduled appointment to start a campaign.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={loading}
              onClick={() =>
                run(async () => {
                  const res = await sim.loadDemoData();
                  setMessage(res.message);
                })
              }
            >
              Load demo data
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={loading}
              onClick={() =>
                run(async () => {
                  const res = await sim.clearDemoData();
                  setMessage(res.message);
                })
              }
            >
              Remove demo data
            </Button>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add facility</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={facilityName} onChange={(e) => setFacilityName(e.target.value)} />
            </div>
            <Button
              type="button"
              disabled={loading || !facilityName.trim()}
              onClick={() =>
                run(async () => {
                  await sim.createFacility(facilityName.trim());
                  setFacilityName("");
                  setMessage("Facility created.");
                })
              }
            >
              Create facility
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add patient</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={patientName} onChange={(e) => setPatientName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input value={patientPhone} onChange={(e) => setPatientPhone(e.target.value)} />
            </div>
            <Button
              type="button"
              disabled={loading || !patientName.trim()}
              onClick={() =>
                run(async () => {
                  await sim.createPatient({
                    name: patientName.trim(),
                    phone: patientPhone.trim() || undefined,
                  });
                  setPatientName("");
                  setPatientPhone("");
                  setMessage("Patient created.");
                })
              }
            >
              Create patient
            </Button>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Book appointment</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <p className="text-sm text-muted-foreground md:col-span-2">
            Candidates must share the same facility and CPT as the canceled slot. Use the demo
            facility for manual bookings unless testing the RadFlow webhook facility.
          </p>
          <div className="space-y-2">
            <Label>Patient</Label>
            <select className={selectCls} value={patientId} onChange={(e) => setPatientId(e.target.value)}>
              <option value="">Select</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Facility</Label>
            <select className={selectCls} value={facilityId} onChange={(e) => setFacilityId(e.target.value)}>
              <option value="">Select</option>
              {facilities.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>CPT</Label>
            <Input value={cptCode} onChange={(e) => setCptCode(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Scheduled</Label>
            <Input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
          </div>
          <div className="md:col-span-2">
            <Button
              type="button"
              disabled={loading || !patientId || !facilityId || !scheduledAt}
              onClick={() =>
                run(async () => {
                  await sim.createAppointment({
                    patient_id: Number(patientId),
                    facility_id: Number(facilityId),
                    cpt_code: cptCode.trim(),
                    scheduled_start_at: new Date(scheduledAt).toISOString(),
                  });
                  setMessage("Appointment created.");
                })
              }
            >
              Create appointment
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appointments</CardTitle>
        </CardHeader>
        <CardContent>
          {appointments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No appointments.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2">ID</th>
                  <th className="py-2">Patient</th>
                  <th className="py-2">Facility</th>
                  <th className="py-2">CPT</th>
                  <th className="py-2">When</th>
                  <th className="py-2">Status</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {appointments.map((a) => (
                  <tr key={a.id} className="border-b border-border/50">
                    <td className="py-2">{a.id}</td>
                    <td className="py-2">{a.patient_name}</td>
                    <td className="py-2">{a.facility_name ?? `#${a.facility_id}`}</td>
                    <td className="py-2">{a.cpt_code}</td>
                    <td className="py-2">{formatDt(a.scheduled_start_at)}</td>
                    <td className="py-2">{a.status}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-1">
                        {a.status === "scheduled" && (
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            disabled={loading}
                            onClick={() =>
                              run(async () => {
                                const res = await backfill.cancelAppointment(a.id);
                                setMessage(res.message);
                                if (res.campaign_created) onCampaignCreated?.();
                              })
                            }
                          >
                            Cancel
                          </Button>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={loading}
                          title="Delete from database"
                          onClick={() =>
                            run(async () => {
                              await sim.deleteAppointment(a.id);
                              setMessage(`Appointment #${a.id} deleted.`);
                            })
                          }
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
      {message && <p className="text-sm text-green-700">{message}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
