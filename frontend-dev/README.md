# Appointment simulator (dev frontend)

Separate Next.js app for backfill **dev data entry** — not bundled with the operator dashboard on port 3000.

| URL | Purpose |
|-----|---------|
| http://localhost:3001/dev/appointments | This app (must run `./run-frontend-dev.sh`) |
| http://localhost:3000/dev/appointments | Same UI on main frontend if you only run `npm run dev` in `frontend/` |
| http://localhost:3000/backfill | View campaigns |

## Run

```bash
# From repo root (after backfill-backend is up)
./run-frontend-dev.sh
```

Or:

```bash
cd frontend-dev
cp .env.example .env.local   # optional
npm install
npm run dev                  # PORT defaults to 3001
```

## Env

| Variable | Default |
|----------|---------|
| `PORT` / `FRONTEND_DEV_PORT` | `3001` |
| `NEXT_PUBLIC_BACKFILL_API_URL` | `http://localhost:8001` |
| `NEXT_PUBLIC_BACKFILL_UI_URL` | `http://localhost:3000` |

UI primitives are imported from `../frontend/components/ui` (shared styling only).
