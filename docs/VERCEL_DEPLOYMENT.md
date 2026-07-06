# Vercel Deployment

This repository deploys as one Vercel Services project:

- Next.js frontend at `/`
- FastAPI backend at `/api`

## Project Setup

1. Import the Git repository into Vercel.
2. Set the project Framework Preset to `Services`.
3. Keep the project root as the repository root.
4. Add the variables from `.env.vercel.example` to Production and Preview.
5. Deploy.

The frontend uses same-origin API requests in production, so
`NEXT_PUBLIC_API_URL` should normally remain unset.

## Required Production Variables

- `DATABASE_URL`
- `OPENROUTER_API_KEY`
- `AUTH_SECRET_KEY`
- `CRON_SECRET`

Use `AI_PROVIDER=openrouter` and `LLM_VALIDATOR_PROVIDER=openrouter`.
Local Ollama URLs are not reachable from Vercel.

## Temporary Direct Admin

To allow Super Admin access without changing the existing database schema, set:

- `DIRECT_ADMIN_ENABLED=true`
- `DIRECT_ADMIN_EMAIL` to the temporary admin email
- `DIRECT_ADMIN_PASSWORD` to a strong temporary password

The matching login and its signed session validation bypass the database.
Remove these variables or set `DIRECT_ADMIN_ENABLED=false` after database-backed
authentication is ready.

## Scheduled Reports

The in-process scheduler is disabled automatically on Vercel. Configure a
Vercel Cron Job to call:

```text
/api/cron/scheduled-reports
```

Vercel sends `Authorization: Bearer <CRON_SECRET>` automatically when the
project has a `CRON_SECRET` environment variable.

Cron frequency depends on the Vercel plan. The endpoint safely processes
reports whose `next_run_at` is due.

## Serverless Storage

The JSON SQL cache and local Chroma store are disabled on Vercel because the
function filesystem is not persistent. Database-backed users, saved reports,
shares, permissions, audit logs, schedules, and mistake records remain
persistent.

## CLI

Vercel Services requires a current CLI:

```powershell
npx vercel@latest login
npx vercel@latest
npx vercel@latest --prod
```
