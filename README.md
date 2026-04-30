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

## Important Database Note

The app reads `.env` from the project root even when the backend is started from `backend/`.

The app needs a direct MySQL connection host to execute SQL. Set either `DATABASE_URL` or `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `.env`. If `DATABASE_URL` is present with placeholder text, the backend ignores it and uses the individual DB fields.

For development AI SQL generation, Gemini is the default provider:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-1.5-flash
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
- `POST /api/reports/query`

Example request:

```json
{
  "question": "Show project summary report for active projects this month",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30",
  "limit": 100,
  "dry_run": true
}
```

## Next Step Before Production

Run live database introspection and reconcile table aliases like `attendance`/`attendances` and `product_task`/`product_tasks` against the actual database. The catalog already records these variants so the application can be tightened quickly once direct DB access is configured.
