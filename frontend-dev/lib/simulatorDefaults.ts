import type { Facility } from "@/types/backfill";

/** Prefer the demo facility when seeding manual appointments in dev. */
export function defaultSimulatorFacilityId(facilities: Facility[]): string {
  if (facilities.length === 0) return "";
  const demo = facilities.find((f) => /demo/i.test(f.name));
  return String((demo ?? facilities[0]).id);
}
