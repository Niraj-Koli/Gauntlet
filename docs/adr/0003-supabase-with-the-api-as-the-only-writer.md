# 0003: Supabase for Postgres, Realtime and Auth, with the API as the only writer

**Status:** accepted

## Context

The original project stored each account as a JSON blob in SQLite and rewrote it on every change, from several processes at once, so updates could be lost. The dashboard polled every few seconds and fetched live prices for every holding on every poll. The rebuild needed a real relational schema, live updates in the browser, and a sign-in for the admin panel.

## Decision

Use Supabase. Its managed Postgres is reached through SQLAlchemy with asyncpg, and Alembic owns the schema. Its Realtime channel pushes row changes to the dashboard, and its Auth signs admins in.

- **Writes:** only the backend writes, as the table owner, inside transactions with row locks.
- **Reads:** row-level security is on for every table. Migration 0003 gives Supabase's anon and authenticated roles read-only access to the dashboard tables, which is what Realtime requires. The command queue and floor state stay private.
- **Sign-in:** the API verifies Supabase access tokens against the project's signing keys (JWKS), and allows only emails in `ADMIN_EMAILS`.

SQLite stays supported for development and the zero-setup demo.

## Consequences

- **No realtime server of our own:** live updates need no custom SSE or LISTEN/NOTIFY layer, and the browser can't write anything, even with the public anon key.
- **One codebase, two databases:** the same code and migrations run on SQLite and Postgres, and the test suite runs on both.
- **Supabase is a dependency:** Realtime and Auth exist only with it. Without it, the dashboard falls back to polling and admin to a static token, and it says so.
- **Postgres-only migration:** migration 0003 does nothing on plain Postgres that lacks Supabase's roles and publication.
