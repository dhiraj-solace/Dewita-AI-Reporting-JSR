# Devita AI Reporting System

FastAPI + Next.js scaffold for natural-language database reporting.

## What Is Included

- Semantic schema catalog built from the supplied DOCX, SQL descriptions, and report CSV.
- Business report catalog for attendance, timesheets, daily/project summaries, week-five reports, efficiency, capacity, rating, markup, change requests, and post-error reports.
- Guarded SQL execution pipeline:
  - Natural-language request
  - Optional AI SQL generation
  - Read-only SQL validation
  - Database execution
  - Structured report response
- Next.js frontend for asking a report question, date filtering, dry runs, SQL inspection, and tabular results.
- Role-based report permissions where Admin assigns report categories/actions to roles.
- Saved report access filtering by role and report category.
- Report audit logging for saved reports and Admin permission changes.
- Model performance tracking for provider/model, generation time, validator time, SQL execution time, and total request time.
- Scheduled report auto-generation for daily, weekly, and monthly reports.
- Super Admin-only scheduled report management with email notifications and report attachments.

## Important Database Note

The app reads `.env` from the project root even when the backend is started from `backend/`.

The app needs a direct MySQL connection host to execute SQL. Set either `DATABASE_URL` or `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `.env`. If `DATABASE_URL` is present with placeholder text, the backend ignores it and uses the individual DB fields.

For development AI SQL generation, Gemini is the default provider:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-1.5-flash
```

Optional SMTP settings for scheduled report email delivery:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=reporting@example.com
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=reporting@example.com
SMTP_FROM_NAME=Devita AI Reporting
SMTP_USE_TLS=true
```

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## API

- `GET /health`
- `GET /api/schema`
- `GET /api/reports/catalog`
- `GET /api/reports/categories`
- `POST /api/reports/query`
- `GET /api/reports/saved?role=Super%20Admin`
- `GET /api/admin/report-permissions`
- `PUT /api/admin/report-permissions`
- `GET /api/admin/report-audit-logs`
- `GET /api/admin/scheduled-reports?actor_role=Super%20Admin`
- `POST /api/admin/scheduled-reports?actor_role=Super%20Admin`
- `PUT /api/admin/scheduled-reports/{id}?actor_role=Super%20Admin`
- `PATCH /api/admin/scheduled-reports/{id}/status?actor_role=Super%20Admin`
- `POST /api/admin/scheduled-reports/{id}/run-now?actor_role=Super%20Admin`
- `GET /api/admin/scheduled-reports/{id}/runs?actor_role=Super%20Admin`
- `GET /api/admin/ai-sql-attempts`

Example request:

```json
{
  "question": "Show project summary report for active projects this month",
  "report_category": "project",
  "current_user_role": "Super Admin",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30",
  "limit": 100,
  "dry_run": true
}
```

## Role-Based Report Permissions

Admin can manage role-to-report access at:

```text
http://localhost:3000/admin/report-permissions
```

Supported roles are seeded from `Super Admin`, `HR`, `Project Manager`, `Team Leader`, and `Team Member`, plus any roles found in the database `roles` table. For each role and report category, Admin can configure:

- View
- Create
- Export
- Save
- View saved reports
- Data scope: `all`, `role`, `team`, `project`, `self`, or `none`

The main reporting page includes an Active Role selector for the current no-auth development phase. That role is sent as `current_user_role`, and the backend checks permissions before report generation, saved report listing, saved report opening, and export.

## Audit and Tracking

The backend creates application tables for operational tracking:

- `ai_sql_attempts`: AI SQL attempts, status, model/provider, timing, result count, feedback, and gold-example approval.
- `saved_reports`: saved report data, report category, and creator role.
- `role_report_permissions`: Admin-managed role-to-report permission matrix.
- `report_audit_logs`: saved report events and role permission changes.
- `scheduled_reports`: dynamic report schedules, filters, recipients, and execution settings.
- `scheduled_report_runs`: run history for automatic/manual schedule executions.

## Scheduled Reports

Only Super Admin can manage scheduled reports at:

```text
http://localhost:3000/admin/scheduled-reports
```

Schedules are database-driven and support:

- daily, weekly, and monthly frequencies
- schedule time
- report category/type
- natural-language report question
- dynamic date presets such as current month, previous month, current week, and previous week
- run-as role
- recipient emails and roles metadata
- email delivery with Excel and PDF attachments when SMTP is configured
- enable/disable
- manual Run Now verification
- run history

A date preset is a dynamic date filter. For example, `current_month` is resolved on the day the schedule runs, so a monthly schedule in May uses May dates and the same schedule in June uses June dates without editing the schedule.

The backend starts a lightweight polling scheduler on FastAPI startup. It checks active due schedules, runs the normal safe `build_report()` pipeline, saves successful reports, emails configured recipients, records run history, and writes audit log events.

## Next Step Before Production

Run live database introspection and reconcile table aliases like `attendance`/`attendances` and `product_task`/`product_tasks` against the actual database. The catalog already records these variants so the application can be tightened quickly once direct DB access is configured.

Before production, replace the temporary Active Role selector with real authentication/session context so the backend derives the user role instead of trusting a frontend-selected role.
