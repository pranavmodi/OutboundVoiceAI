# Cancellation Backfill Agent — Architecture Decision: Independent System with Shared Frontend

**Status:** Adopted — overrides parts of [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)
**Scope:** Applies to the Cancellation Backfill Agent only. The existing outbound caller is unchanged.

---

## TL;DR

The Cancellation Backfill Agent will be built as an **independent system**. Only the operator-facing **frontend is shared** with the existing outbound caller. The backend service and the database are separate.

| Layer | Sharing |
|---|---|
| Frontend (admin dashboard) | **Shared.** Hosts two distinct agent areas: one for the existing outbound caller (unchanged) and one for the new Cancellation Backfill Agent. |
| Backend service | **Separate.** New service. No shared application code with the outbound caller. |
| Database | **Separate.** New database with its own schema. The `BackfillCampaign` / `BackfillCandidate` / `BackfillActionLog` tables do **not** live in the outbound caller's database. |

---

## What changes vs. the spec

[`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md) was written assuming the agent would be embedded inside the existing outbound AI platform. This decision overrides that assumption.

The following spec statements are **superseded** by this document. They are listed by their location in the spec so they can be updated or annotated later if the team wants the spec to remain canonical.

| Spec location | Original text | Status under this decision |
|---|---|---|
| 📌 Purpose (line ~13) | "This agent must be implemented inside the existing outbound AI platform, not as a standalone service or separate workflow." | **Overridden.** The agent is its own service; only the frontend is shared. |
| 🔭 Scope → In Scope (line ~30) | "Reuse existing outbound AI holiday, quiet-hour, and calling-hour enforcement" | **Replaced.** The new backend implements its own enforcement (or calls a shared service via an explicit integration). It does not import the outbound caller's code. |
| 🗄️ Data Model (line ~168) | "All tables live in `tenant_db`." | **Overridden.** Tables live in the backfill agent's own database, not in `tenant_db`. |
| ⚙️ Admin Settings → Shared Settings Inherited from Platform (line ~546) | "Holiday dates, do-not-call windows, opt-out enforcement, logging retention, SMS/voice provider routing." | **Re-scoped.** These are no longer implicitly shared. Each is either duplicated in the new system or coordinated via an explicit cross-service contract. See [§ Implications](#implications) below. |
| 🏗️ Non-Functional Requirements → Maintainability (line ~576) | "Reuse existing outbound abstractions. No hardcoded business hours, holidays, or message branching outside shared systems." | **Replaced.** No reuse of outbound caller code. New abstractions are owned by the new backend. |
| 🔗 Integration Points → Outbound admin UI (line ~587) | "Single dashboard, agent selection, campaigns, settings, reports" | **Retained, with clarification.** The dashboard remains a single frontend, but each agent area calls its own backend. |

The full spec body — trigger rules, candidate selection, outreach strategy, status models, UI requirements, acceptance criteria — continues to apply unchanged. Only the architectural framing differs.

The earlier integration analysis in [`analysis.md`](./analysis.md) was also written under the embedded assumption. Its "What's Similar (Shared Infrastructure)" table and "Phase 1: Multi-Agent Foundation" plan are now obsolete; the gap analysis itself (what features need to be built) is still informative.

---

## Frontend integration

The frontend is the only shared surface. The existing outbound caller dashboard must remain **functionally and visually unchanged**.

### What exists today

- App shell: [`frontend/app/page.tsx`](../../frontend/app/page.tsx) — Next.js client component, owns the dashboard layout, tabs, and data hooks.
- Dashboard cards: [`frontend/components/dashboard/`](../../frontend/components/dashboard/) — `QueueStatusCard`, `PatientQueueCard`, `ActiveCallCard`, `CallHistoryCard`, `DispatcherEventsCard`, `KpiBar`, `AuditLogCard`, `TranscriptBrowserCard`.
- Operator console: [`frontend/components/console/`](../../frontend/components/console/).
- API client: [`frontend/hooks/useApi.ts`](../../frontend/hooks/useApi.ts), [`frontend/hooks/useWebSocket.ts`](../../frontend/hooks/useWebSocket.ts) — all currently hit the outbound caller's FastAPI backend (single base URL).

### What needs to change

1. **Introduce an agent-selection shell** at the top level of the dashboard. The current top-level content (queue, active call, history, etc.) moves under an "Outbound Caller" agent area without any internal changes.
2. **Add a second agent area** for Cancellation Backfill, with its own Campaigns / Settings / Reports tabs as described in the spec's [🖥️ UI Requirements](./cancellation-backfill-spec.md) section.
3. **Route data calls per agent area** — the existing API hooks continue to point at the outbound caller backend; new hooks for the backfill area point at the new backend (separate base URL, separate auth scope).
4. **Keep the outbound caller's URL paths stable** so any existing bookmarks, links, and operator muscle memory continue to work. Adding a new top-level route (e.g. `/agents/cancellation-backfill`) for the new area is preferable to restructuring existing routes.

### Constraints

- No new dependencies on outbound-caller domain types from the backfill area, and vice versa. Shared chrome (layout, nav, theme, auth shell) is the only allowed coupling.
- The agent selector must surface enable/disable status inline per the spec, but each agent's enable/disable state is owned by its own backend.

---

## Backend boundary

The new service is **separate** from the existing FastAPI app at [`app/`](../../app/). Specifically:

- No reuse of the existing routers under [`app/api/`](../../app/api/) (`dashboard.py`, `dispatcher.py`, `settings.py`, `audit.py`, `auth.py`, `intake.py`, `scenarios.py`, `v2_test.py`, `websocket.py`).
- No reuse of the existing services under [`app/services/`](../../app/services/) (orchestrator, dispatcher, voice services, SMS service, notification services, etc.).
- No reuse of providers under [`app/providers/`](../../app/providers/) (settings, patient, call-log, queue).

The new backend can be implemented in whatever stack the team chooses; nothing in this decision requires it to be FastAPI. It exposes its own HTTP API consumed by the new frontend agent area, and (where required) talks to the outbound caller backend via explicit, versioned integration points — not by importing code.

---

## Database boundary

The backfill agent's tables (`BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog`, plus any appointment / facility / patient projection it requires) live in its **own database**. They do not share a connection, schema, or migration history with the outbound caller's database.

- Outbound caller migrations remain in [`alembic/versions/`](../../alembic/versions/) (25 migrations as of this writing). The new backend does not run against this Alembic environment.
- The new system maintains its own migration tool/history.
- Cross-DB queries are not permitted; any data the new system needs about patients, facilities, or appointments is either replicated into its own DB or fetched over an API the outbound caller exposes (see [Implications](#implications)).

---

## Implications

Several capabilities the spec assumed were "shared infrastructure" are no longer free. Each must be addressed explicitly:

| Capability | Spec assumption | Reality under this decision |
|---|---|---|
| Holiday calendar | Inherited from outbound platform | New service maintains its own list, or fetches via a shared HTTP endpoint the outbound caller exposes. Decide which. |
| Business / contact hours enforcement | Reuse existing rules | Re-implement in the new backend. The existing logic in [`app/providers/settings_provider.py`](../../app/providers/settings_provider.py) is a reference, not a dependency. |
| Opt-out / suppression list | Shared enforcement | Either replicated into the new DB, or read via API from the outbound caller. Must be coordinated — a patient opted out in one system must be respected in the other. |
| SMS / voice provider routing | Shared Twilio account & numbers | Decide whether the new system shares the same Twilio account/numbers (creates rate-limit and inbound-routing coupling that must be designed) or uses its own. |
| Inbound SMS webhook | Single endpoint on the existing app | If Twilio is shared, the inbound SMS webhook must route YES/NO replies to the correct system. Recommended: webhook lands on a thin dispatcher that routes by campaign/agent context. |
| Patient / appointment data | Read directly from outbound caller's DB | Replace with API reads or a replication pipeline. |
| Logging / audit trail | Shared `AuditEventRow` table | New system has its own audit storage. Unified operator view (if needed) is a frontend concern. |
| Call recording / transcripts | Shared transcript store | Separate. The frontend may surface both systems' transcripts side-by-side if needed. |

These are non-trivial. The team should make explicit decisions on each before the spec's existing acceptance criteria can be evaluated against the new architecture.

---

## Open questions

1. **Twilio account ownership** — shared with the outbound caller, or separate? Affects inbound SMS routing, rate limits, and number pooling.
2. **Patient / appointment data source** — API reads from the outbound caller, a replication pipeline, or a separately-fed copy from RadFlow?
3. **Opt-out reconciliation** — single source of truth, or two systems syncing? Whichever it is, must be defined before launch.
4. **Auth** — does the shared frontend use one session for both agent areas, or does each backend authenticate independently? Single session is the better operator experience but requires a coordinated auth model.
5. **Cross-agent reporting** — when an operator wants "all AI outreach activity," does that view exist? Where does it pull from?

---

## Cross-references

- Spec: [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)
- Prior integration analysis (now partially obsolete): [`analysis.md`](./analysis.md)
- Outbound caller frontend: [`frontend/app/page.tsx`](../../frontend/app/page.tsx), [`frontend/components/dashboard/`](../../frontend/components/dashboard/)
- Outbound caller backend: [`app/`](../../app/), routers under [`app/api/`](../../app/api/), services under [`app/services/`](../../app/services/)
- Outbound caller migrations: [`alembic/versions/`](../../alembic/versions/)
