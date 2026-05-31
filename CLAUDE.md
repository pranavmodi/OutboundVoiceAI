# Repo guide for the coding agent

This repository hosts **two independent AI outreach systems** that share **only a frontend**. Treat them as separate codebases that happen to live in one repo.

| System | Backend location | Database | Status | Canonical docs |
|---|---|---|---|---|
| **Outbound Caller** (existing, in production) | [`app/`](./app/) | Outbound DB (Alembic at [`alembic/versions/`](./alembic/versions/)) | Working — do not break | [`scheduling-agent-spec.txt`](./scheduling-agent-spec.txt), [`docs/`](./docs/) |
| **Cancellation Backfill** (new, scaffolded) | [`backfill-backend/`](./backfill-backend/) | Separate DB (Alembic at [`backfill-backend/alembic/`](./backfill-backend/alembic/)) | Skeleton only — health endpoint, no domain code | [`docs/cancellation-backfill/cancellation-backfill-spec.md`](./docs/cancellation-backfill/cancellation-backfill-spec.md), [`docs/cancellation-backfill/architecture.md`](./docs/cancellation-backfill/architecture.md), [`docs/cancellation-backfill/analysis.md`](./docs/cancellation-backfill/analysis.md) |
| **Shared frontend** | [`frontend/`](./frontend/) | n/a | Working — both agents render under route group `(agents)/` | [`docs/cancellation-backfill/architecture.md`](./docs/cancellation-backfill/architecture.md) § Frontend integration |

## Hard rules

These boundaries are load-bearing — the cancellation backfill agent was deliberately scoped as an independent system. Violating them defeats the architecture.

1. **No cross-imports between `app/` and `backfill-backend/`.** Neither side imports modules, types, or models from the other. They are two Python projects that happen to share a directory tree.
2. **Separate databases.** `app/` reads/writes the outbound DB (`DATABASE_URL`). `backfill-backend/` reads/writes its own DB (`BACKFILL_DATABASE_URL`). No cross-DB queries. If the backfill system needs patient/appointment data, fetch it over HTTP or replicate it — do not point its session at the outbound DB.
3. **Separate Alembic environments.** Outbound migrations live at [`alembic/versions/`](./alembic/versions/); backfill migrations live at [`backfill-backend/alembic/versions/`](./backfill-backend/alembic/versions/). Never add a migration for one system into the other's tree.
4. **Outbound caller's UI is frozen except for the new shared chrome.** The existing dashboard at `/`, plus `/admin`, `/analytics`, and `/login`, must remain functionally and visually unchanged. The only addition is the `AgentShell` top nav rendered by [`frontend/app/(agents)/layout.tsx`](./frontend/app/(agents)/layout.tsx).
5. **Frontend coupling is limited to shared chrome.** [`frontend/components/agents/AgentShell.tsx`](./frontend/components/agents/AgentShell.tsx) is the only allowed shared surface between the two agent areas. Each agent's pages, hooks, and types are otherwise isolated. Backfill code should not import from outbound dashboard components and vice versa.
6. **Per-agent API hooks.** [`frontend/hooks/useApi.ts`](./frontend/hooks/useApi.ts) hits the outbound backend (`NEXT_PUBLIC_API_URL`). [`frontend/hooks/useBackfillApi.ts`](./frontend/hooks/useBackfillApi.ts) hits the backfill backend (`NEXT_PUBLIC_BACKFILL_API_URL`). Don't merge them, don't share the base URL.
7. **The spec's "shared infrastructure" assumptions are obsolete.** The spec text in `cancellation-backfill-spec.md` predates the architecture decision and assumes embedding inside the outbound platform (shared `tenant_db`, shared holiday calendar, shared opt-out list, etc.). The override is documented in [`docs/cancellation-backfill/architecture.md`](./docs/cancellation-backfill/architecture.md) — defer to that doc when the two conflict.

## Frontend layout

Next.js App Router with a route group for both agent areas:

```
frontend/app/
├── layout.tsx                     # root shell (Tailwind, fonts, tooltip provider)
├── (agents)/                      # route group — invisible in URL
│   ├── layout.tsx                 # wraps both agents in AgentShell
│   ├── page.tsx                   # outbound caller dashboard at /  (DO NOT BREAK)
│   └── backfill/page.tsx          # cancellation backfill at /backfill
├── admin/, analytics/, login/     # unchanged outbound-only pages, no AgentShell
└── globals.css
```

Route groups (`(agents)/`) do not change URLs. The outbound dashboard's URL is still `/`.

## Dev commands

```bash
# Outbound caller backend
./run-backend.sh                            # FastAPI on :8000 from app/

# Cancellation backfill backend
./backfill-backend/run.sh                   # FastAPI on :8001 from backfill-backend/app/

# Shared frontend (proxies to whichever backend each hook targets)
./run-frontend.sh                           # Next.js on :3000

# Dev-only appointment simulator (:3001) — or use http://localhost:3000/dev/appointments
./run-frontend-dev.sh                       # Next.js on :3001
./run-backfill-ui.sh                        # Starts :3001 simulator + :3000 operator UI together
```

Required env (see [`.env.example`](./.env.example) and [`backfill-backend/.env.example`](./backfill-backend/.env.example)):

- `NEXT_PUBLIC_API_URL` — outbound backend URL (default `http://localhost:8000`)
- `NEXT_PUBLIC_BACKFILL_API_URL` — backfill backend URL (default `http://localhost:8001`)
- `BACKFILL_DATABASE_URL` — separate DB for the backfill service
- `BACKFILL_BACKEND_PORT` — defaults to 8001

## Developing one agent without the other

The backfill agent area (`/backfill` + `backfill-backend/`) can be developed without running, installing, or configuring any part of the outbound caller. The full runbook — setup, port-collision handling, CORS, verification curls, common failure modes — lives at [`docs/cancellation-backfill/developing-independently.md`](./docs/cancellation-backfill/developing-independently.md). Read it before trying to start a partial stack.

## When in doubt

- If a change touches **both** systems, stop and ask. Cross-cutting changes likely violate a boundary above.
- If the spec and the architecture doc disagree, the architecture doc wins.
- If you're adding a feature to the backfill system, prefer building it inside `backfill-backend/` even if a similar capability exists in `app/`. The duplication is intentional.
