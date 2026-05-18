# Developing the Cancellation Backfill Agent Independently

This is the runbook for working on `/backfill` (frontend) and `backfill-backend/` (backend) **without** running, installing, or configuring any part of the outbound caller.

The two systems are deliberately decoupled per [`architecture.md`](./architecture.md). The boundary rules are codified in the [`CLAUDE.md`](../../CLAUDE.md) at the repo root.

---

## What you need running

Two processes, full stop:

| Process | Path | Default port | What it serves |
|---|---|---|---|
| Backfill backend (FastAPI) | [`backfill-backend/`](../../backfill-backend/) | 8011 (was 8001 — see note below) | `/api/health`, future campaign/candidate/settings endpoints |
| Shared frontend (Next.js dev) | [`frontend/`](../../frontend/) | 3000 (falls through to 3001/3002/3003 if busy) | `/backfill` page + AgentShell chrome |

## What you do NOT need

- The outbound caller backend (`app/`)
- The outbound caller's `outboundvoice` database / its Alembic state
- Twilio, OpenAI, Gemini, FreePBX, RadFlow, Redis, or any outbound integration
- Anything else listed under "Integration Points" in [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)

The frontend's auth middleware ([`frontend/middleware.ts`](../../frontend/middleware.ts)) treats `/backfill` as public, so navigating to it does not redirect to `/login` (which would require the outbound auth API). The outbound dashboard at `/`, plus `/admin` and `/analytics`, are still gated as before — try to visit them and you'll get redirected, which is the correct behavior when the outbound backend is down.

## Database

The backfill agent has its own postgres database, named `backfill`. The architecture only requires a **separate logical database** — the physical server can be the same one the outbound caller uses. In current dev, both databases live on the team's remote postgres at `10.254.99.34:5432`, owned by the `precise` user:

```
postgres @ 10.254.99.34:5432
├── outboundvoice  (outbound caller — DO NOT touch from this service)
└── backfill       (this service's database)
```

`backfill-backend/.env` ships with:
```
BACKFILL_DATABASE_URL=postgresql+asyncpg://precise:password@10.254.99.34:5432/backfill
```

If you ever need to recreate the database from scratch (e.g. clean slate, new dev host):

```bash
# precise must already have CREATEDB privilege on the remote — it does.
PGPASSWORD='password' psql -h 10.254.99.34 -U precise -d postgres \
  -c "CREATE DATABASE backfill OWNER precise;"
```

For a fully local-postgres setup (no VPN needed), see the alternative in `backfill-backend/.env.example` — point `BACKFILL_DATABASE_URL` at `localhost:5432/backfill` once you've provisioned that local DB yourself.

Migrations live at [`backfill-backend/alembic/versions/`](../../backfill-backend/alembic/versions/) — independent of the outbound caller's `alembic/` at the repo root. No tables exist yet; the first Alembic revision will land when the three core tables from the spec (`BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog`) are implemented.

---

## First-time setup

```bash
# 1. Backfill backend venv + deps
cd backfill-backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp .env.example .env                          # edit DATABASE_URL / port as needed
cd ..

# 2. Frontend deps (only if not already installed)
cd frontend
npm install
cd ..

# 3. Frontend env — point hooks at localhost
# Edit frontend/.env.local (gitignored) and ensure it has:
#   NEXT_PUBLIC_BACKFILL_API_URL=http://localhost:8011
# (and NEXT_PUBLIC_API_URL for outbound, even if you won't run outbound —
#  the outbound dashboard at / will fail-soft when it's missing)
```

The `.env` and `.env.local` files are gitignored — they hold per-developer config.

## Each dev session

```bash
# Terminal 1 — backfill backend
cd backfill-backend
./run.sh                                       # uses .venv/bin/uvicorn, --reload on

# Terminal 2 — shared frontend
cd frontend
npm run dev                                    # binds 3000 (or whatever PORT you set)
```

Then open <http://localhost:3000/backfill> in a browser. The page should render and the "Backend status" card should flip from "Checking backfill-backend..." to "Backfill backend is reachable" within a second.

---

## When the default ports are taken

Both Next.js and uvicorn can run on alternate ports — you just need three pieces to agree.

### Backfill backend on a non-default port

Edit `backfill-backend/.env`:
```bash
BACKFILL_BACKEND_PORT=8012     # or whatever's free
```
Restart `./run.sh`.

Then update `frontend/.env.local` to match:
```bash
NEXT_PUBLIC_BACKFILL_API_URL=http://localhost:8012
```
Restart the Next.js dev server (env changes are picked up on restart, not on hot-reload).

### Frontend on a non-default port

```bash
cd frontend
PORT=3005 npm run dev
```

Then either:
- Edit `backfill-backend/.env` to add the new port to `BACKFILL_CORS_ORIGINS` (comma-separated), or
- Use a port already in the defaulted list (`3000`, `3001`, `3002`, `3003`).

Restart the backfill backend after changing CORS — uvicorn's `--reload` watches Python source, not `.env`.

### Diagnosing port collisions

```bash
ss -lntp 2>/dev/null | grep -E ":(3000|3001|3002|3003|8011) "
# or just probe:
for p in 3000 3001 3002 3003 3004 3005 8011 8012; do
  timeout 1 python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',$p))" 2>/dev/null \
    && echo "$p free" || echo "$p busy"
done
```

---

## Verifying the loop is wired correctly

Three checks in escalating order:

```bash
# 1. Backfill backend alone
curl -s http://localhost:8011/api/health
# expect: {"status":"ok","service":"backfill-backend"}

# 1b. Backend ↔ database
curl -s http://localhost:8011/api/db-health
# expect: {"status":"ok","database":"backfill","user":"precise"}
# error payload: {"status":"error","detail":"..."} — see "Common failure modes"

# 2. CORS allows your frontend origin
curl -sI -X OPTIONS http://localhost:8011/api/health \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
# expect: access-control-allow-origin: http://localhost:3000  (or whatever your frontend port is)

# 3. Frontend page renders without auth redirect
curl -s -o /dev/null -w "code=%{http_code}\n" http://localhost:3000/backfill
# expect: code=200
```

If all three pass, opening `/backfill` in a browser will show the green-check "Backfill backend is reachable" state.

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `./run.sh` exits with `ModuleNotFoundError: No module named 'pydantic_settings'` | Shell's PATH `uvicorn` ran instead of `.venv/bin/uvicorn` | The current `run.sh` uses `.venv/bin/uvicorn` explicitly — re-pull `feature/backfill-codebase-structure` or later if you see this. |
| `/backfill` redirects to `/login` | Middleware is missing `/backfill` in `PUBLIC_PATHS` | Re-check [`frontend/middleware.ts`](../../frontend/middleware.ts) — the `PUBLIC_PATHS` const should include `"/backfill"`. |
| "Backfill backend not reachable" on `/backfill` page | Backend down, port mismatch, or CORS blocked | Run the three curl checks above and find which one fails. |
| `Address already in use` on uvicorn or Next.js startup | Some other process holds the default port | Pick a different port and update all three places (backend `.env`, frontend `.env.local`, backend CORS list). |
| `npm run dev` reports build OK but `/backfill` returns 404 | Stale `.next/` cache from a build before the page was added | `rm -rf frontend/.next` and restart `npm run dev`. |
| Cross-origin GET works in `curl` but fails in the browser | CORS preflight rejected — see the preflight check command above | Add your frontend origin to `BACKFILL_CORS_ORIGINS` and restart the backend. |
| `/api/db-health` returns `{"status":"error","detail":"..."}` with `connection refused` | Network can't reach 10.254.99.34 (VPN down, or no route from this host) | Bring up your VPN, or switch `BACKFILL_DATABASE_URL` to a local postgres. |
| `/api/db-health` returns `password authentication failed` | Credentials in `BACKFILL_DATABASE_URL` don't match `precise/password` (or whatever role you set up) | Verify with `psql` directly using the same URL, then correct `.env`. |
| `/api/db-health` returns `database "backfill" does not exist` | DB hasn't been created yet on this server | Run the `CREATE DATABASE backfill OWNER precise;` snippet in the "Database" section above. |

---

## What's intentionally still coupled (and why it's fine for dev)

- **`AgentShell` top nav links to `/`** — if you click "Outbound Caller" while the outbound backend is down, you'll get redirected to `/login` (which also fails). That's acceptable in this workflow: you're developing backfill, not outbound. If you want to silence the dead link, comment out the Outbound entry in [`frontend/components/agents/AgentShell.tsx`](../../frontend/components/agents/AgentShell.tsx) locally — don't commit that change.
- **Root layout + Tailwind config + UI primitives** — shared across both agent areas. Changing them affects outbound's appearance, which violates the spirit of "outbound UI is frozen" (see [`CLAUDE.md`](../../CLAUDE.md) hard rule #4). Touch with care.
- **The `useApi` hook** — still imported by outbound pages and the AgentShell-adjacent code. The backfill area should never import it; use [`useBackfillApi`](../../frontend/hooks/useBackfillApi.ts) instead.

---

## Long-term auth note

The `/backfill` middleware bypass is a dev-mode escape hatch, not the production auth model. Production needs the backfill area to authenticate against its own backend — that's open question #4 in [`architecture.md`](./architecture.md). When that decision is made, the bypass goes away and `/backfill` becomes auth-required against `backfill-backend/`.

For now, treat the bypass as something you can rely on locally but should not deploy as-is.
