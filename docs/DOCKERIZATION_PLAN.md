# OutboundVoiceAI — Dockerization Plan

Context and implementation steps for containerizing the OutboundVoiceAI stack.
This document captures the design decisions so any future session can pick up
where we left off without re-deriving everything.

---

## Reference implementation

Pattern is modeled after the sibling project at `../emailtag`, which already
runs in production with Docker. Key things borrowed from there:

- `network_mode: host` (no internal bridge network, services reach each other
  via localhost — simplest model, matches how everything already runs bare-metal)
- TLS terminated by uvicorn itself (`--ssl-keyfile` / `--ssl-certfile`)
  instead of a reverse proxy
- External Postgres (not containerized) — keep using the existing DB host
- Non-root user + healthcheck baked into the image
- Single Dockerfile for the Python app, `command` overridden per service if needed
- Next.js frontend uses `output: "standalone"` for a small runtime image

See `../emailtag/Dockerfile`, `../emailtag/docker-compose.yml`, and
`../emailtag/frontend/settings2/Dockerfile` as working references.

---

## Architecture: 2 containers

| Container | Purpose | Port |
|-----------|---------|------|
| `outboundvoice-web` | FastAPI backend — REST API, WebSockets, Twilio media streams, voice AI, dispatcher, SMS, HL7 | 8003 |
| `outboundvoice-frontend` | Next.js dashboard UI | 3002 |

**Not containerized** (external services we already connect to):

- PostgreSQL — stays at `10.254.99.34:5432`, connected via `DATABASE_URL` in `.env`
- Twilio — cloud
- OpenAI / Gemini — cloud
- RadFlow API — external
- FreePBX / Asterisk — existing phone system

emailtag has 5 containers because it uses Celery (+ Flower) and a separate
MCP server. OutboundVoiceAI does not — the dispatcher runs as an asyncio
task inside the main backend process — so 2 containers is sufficient.

---

## Files to create

### 1. `Dockerfile` (project root — backend)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8003 --ssl-keyfile certs/privkey.pem --ssl-certfile certs/fullchain.pem"]
```

Notes:
- `ffmpeg` is needed for audio transcoding (recording downloads, mulaw/PCM
  conversions). `curl` is used for the healthcheck.
- Alembic runs `upgrade head` on every startup — safe to run repeatedly,
  and keeps schema in sync when new migrations land.
- TLS certs are read from `/app/certs` which is a read-only volume mount.

### 2. `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3002
CMD ["node", "server.js"]
```

Uses Next.js standalone output (requires `output: "standalone"` in
`next.config.mjs`) so the runtime image only contains the minimal files
needed to run the app.

### 3. `docker-compose.yml` (project root)

```yaml
services:
  web:
    build: .
    container_name: outboundvoice-web
    network_mode: host
    env_file:
      - .env
    volumes:
      - ./certs:/app/certs:ro
      - ./app/audio:/app/app/audio
      - ./recordings:/app/recordings
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: outboundvoice-frontend
    network_mode: host
    environment:
      - PORT=3002
      - HOSTNAME=0.0.0.0
      - NEXT_PUBLIC_API_URL=https://outbound.mediflow360.com
    restart: unless-stopped
```

Volume mounts explained:

- `./certs:/app/certs:ro` — TLS certs (read-only); renewed on the host
- `./app/audio:/app/app/audio` — cached TTS greeting files (`ai_greeting.mp3`,
  `ai_response.mp3`); persists across container rebuilds
- `./recordings:/app/recordings` — downloaded Twilio call recordings;
  required so the audio playback endpoint (`/api/calls/{id}/audio`) can
  still find recorded MP3s after a rebuild

### 4. `.dockerignore` (project root)

```
node_modules
.venv
__pycache__
*.pyc
.next
recordings/
tests/
docs/
*.csv
*.log
.env.local
.git
```

---

## Pre-work required before `docker compose up`

1. **Add `output: "standalone"` to `frontend/next.config.mjs`**

   ```js
   /** @type {import('next').NextConfig} */
   const nextConfig = {
     reactStrictMode: true,
     output: "standalone",
   };

   export default nextConfig;
   ```

2. **Create `certs/` directory** at the project root with `privkey.pem`
   and `fullchain.pem`. These are the same certs the existing port-8444
   uvicorn process already reads. They likely come from Let's Encrypt
   somewhere on the host — we need to copy or symlink them in.

   Alternative: drop TLS from uvicorn and put Caddy in front. The
   emailtag pattern embeds TLS in the app, so we'll match that for now.

3. **Confirm `DATABASE_URL`** in `.env` points to the right Postgres host.
   With `network_mode: host`, the container reaches `10.254.99.34:5432`
   exactly the same way the bare-metal process does today — no change needed.

4. **Create `recordings/` directory** on the host (or confirm it exists —
   `app/services/recording_service.py` currently writes MP3s somewhere;
   wherever that is, expose it as a volume).

---

## Deploy sequence

### First-time
```bash
# From the project root
docker compose build
docker compose up -d
docker compose logs -f web      # watch backend logs
docker compose logs -f frontend # watch frontend logs
```

### Verify after startup
- `curl -k https://localhost:8003/health` → should return `ok`
- Visit `https://outbound.mediflow360.com` in browser → dashboard loads
- Check alembic ran: `docker compose logs web | grep -i alembic`
- Place a test call via the dashboard → verify Twilio webhook reaches
  the container (watch for `[CallOrchestrator]` log lines)
- Confirm dispatcher picks up a patient (watch for `[Dispatcher]` logs)

### Migrate from current bare-metal process
1. Stop the running uvicorn processes:
   - Port 8003 (dev): PID varies, `ps aux | grep 'port 8003'`
   - Port 8444 (prod): PID varies, `ps aux | grep 'port 8444'`
2. `docker compose up -d`
3. Twilio webhook URL (`PUBLIC_BASE_URL` in `.env`) should already point
   at `https://outbound.mediflow360.com` which reaches wherever uvicorn
   now listens (host networking means same port bindings).

---

## Follow-ups / optional

1. **Auto-start on reboot** — `restart: unless-stopped` handles container
   restart after crashes, but you also need Docker itself to start on boot:
   `sudo systemctl enable docker`

2. **SSL cert renewal** — if Let's Encrypt renews certs on the host, the
   container needs to either be restarted after renewal or watch the
   cert file for changes. A simple cron:
   ```
   0 3 * * * certbot renew && docker compose restart web
   ```

3. **CI/CD** — GitHub Actions to build + push images to a registry on
   merge to main, then pull + redeploy on the server. Skip for now unless
   we're deploying to multiple environments.

4. **Secrets** — `.env` is currently checked in to the local filesystem.
   For production, consider using Docker secrets or an env var manager
   so `OPENAI_API_KEY`, `TWILIO_AUTH_TOKEN`, `APP_PASSWORD`,
   `GEMINI_API_KEY`, `APP_SESSION_SECRET` etc. aren't sitting in a file
   on disk.

5. **Postgres backup** — not part of the Docker setup (external DB), but
   worth confirming the backup strategy for `10.254.99.34:5432`.

---

## Risks / watch-outs

| Risk | Mitigation |
|------|------------|
| Port conflicts with `network_mode: host` | Stop all existing uvicorn/node processes before `docker compose up` |
| Lost audio files on rebuild | Volume mount `./app/audio` and `./recordings` (already in the compose) |
| Cert file format | Uvicorn expects PEM format; Let's Encrypt outputs PEM by default |
| Frontend hot-reload in dev | The production image doesn't support hot reload. Use `npm run dev` outside Docker for local dev, or make a `docker-compose.dev.yml` override |
| Alembic migration hangs on startup | If a migration takes longer than the healthcheck `start_period` (20s), bump it |
| Twilio can't reach container | With `network_mode: host`, Twilio reaches the container exactly the same way it reaches the current process — via `PUBLIC_BASE_URL`. No change needed. |

---

## Status

- [ ] Step 1: prep work (next.config.mjs, certs/, .dockerignore)
- [ ] Step 2: write Dockerfile, frontend/Dockerfile, docker-compose.yml
- [ ] Step 3: local build + smoke test
- [ ] Step 4: cutover from bare-metal process
- [ ] Step 5 (optional): systemd / auto-start
- [ ] Step 6 (optional): CI/CD pipeline
