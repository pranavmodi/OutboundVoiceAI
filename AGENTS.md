# Agent instructions

All coding-agent rules for this repository live in [`CLAUDE.md`](./CLAUDE.md).

It documents the two-system architecture (outbound caller in `app/`, cancellation backfill in `backfill-backend/`, shared frontend in `frontend/`), the hard boundaries between them (no cross-imports, separate databases, separate Alembic environments), the route-group layout in the frontend, and the dev commands for each system.

Whatever agent or IDE you're running in, read `CLAUDE.md` before making changes.
