# AI-Based Reporting System - Project Planning Document

## 1. Purpose of This Document

This document explains how to plan, design, and develop an AI-based reporting system similar to the Devita AI Reporting System.

The goal of this type of system is simple:

> Allow users to ask business questions in normal language, convert those questions into safe SQL queries, run the queries on a database, and display the result as a report.

This document can be used before coding a similar project.

## 2. Business Problem

Most companies store useful data in databases, but non-technical users cannot directly write SQL queries. They depend on developers or analysts to create reports.

An AI reporting system solves this by allowing users to ask questions like:

- "Show active projects this month"
- "Give me revision summary by project"
- "Show employee attendance for April 2026"
- "Which projects used more actual hours than planned?"

The system converts the question into SQL, validates the SQL, runs it safely, and shows the result in a readable format.

## 3. Target Users

The system should be planned for these users:

- Business users who need reports but do not know SQL.
- Project managers who need project, task, revision, or performance reports.
- Admin users who review AI-generated SQL and approve correct examples.
- Developers who maintain schema, prompts, validation logic, and APIs.
- Management users who need quick summaries from operational data.

## 4. Main Features

The system should include:

- Natural-language report input.
- Report category selection or auto-detection.
- Database schema reading.
- AI SQL generation.
- SQL safety validation.
- Schema validation.
- Query execution.
- Report table display.
- Generated SQL preview.
- Error and retry handling.
- Admin review dashboard.
- Storage of successful and failed AI SQL attempts.
- Reusable report templates.
- Export options such as CSV, Excel, or PDF.

## 5. High-Level System Architecture

```mermaid
flowchart LR
  User["User"] --> UI["Frontend UI"]
  UI --> API["Backend API"]
  API --> Intent["Intent / Category Detection"]
  API --> Schema["Schema Service"]
  API --> Prompt["Prompt Builder"]
  Prompt --> AI["AI Model"]
  AI --> SQL["Generated SQL"]
  SQL --> Guard["SQL Safety + Schema Validation"]
  Guard --> DB["Database"]
  DB --> Result["Report Result"]
  Result --> UI
  API --> Audit["Attempt / Feedback Storage"]
```

## 6. Recommended Technology Stack

### Frontend

- Next.js or React
- TypeScript
- Table component for report output
- Form controls for category, date range, filters, and provider selection

### Backend

- FastAPI, Django, Express, or similar API framework
- Pydantic or equivalent request/response validation
- SQLAlchemy or equivalent database layer
- HTTP client for AI provider calls

### Database

- MySQL, PostgreSQL, SQL Server, or any relational database
- Read-only database user for report execution
- Separate tables for AI attempts, feedback, and approved examples

### AI Providers

- OpenAI
- Gemini
- OpenRouter
- Local Ollama model

The system should be provider-independent so the model can be changed later.

## 7. Development Phases

### Phase 1: Requirement Gathering

Before coding, collect:

- List of reports users need.
- List of user roles.
- Database tables involved.
- Filters required by users.
- Output format needed.
- Security restrictions.
- Examples of real user questions.

Deliverables:

- Requirement document.
- Report list.
- User role list.
- Sample questions.

### Phase 2: Database Study

Understand the database before building AI logic.

Tasks:

- List all important tables.
- Identify primary keys and foreign keys.
- Document table relationships.
- Identify important date columns.
- Identify status columns.
- Identify business metrics.

Deliverables:

- Schema catalog.
- ER diagram.
- Table description document.
- Relationship document.

### Phase 3: Report Catalog Planning

Create a report catalog before writing prompts.

Each report should define:

- Report name.
- Report category.
- Required tables.
- Required columns.
- Filters.
- Metrics.
- Example questions.
- Example SQL if available.

Example:

```json
{
  "name": "Project Summary Report",
  "category": "project",
  "tables": ["projects", "product_task"],
  "metrics": ["total_tasks", "completed_tasks", "progress_percentage"],
  "filters": ["date_range", "project_status", "client"]
}
```

### Phase 4: Backend API Planning

Plan APIs clearly.

Recommended endpoints:

- `GET /health`
- `GET /api/schema`
- `POST /api/schema/refresh`
- `GET /api/reports/catalog`
- `GET /api/reports/categories`
- `POST /api/reports/query`
- `GET /api/admin/ai-sql-attempts`
- `POST /api/admin/ai-sql-attempts/{id}/review`
- `GET /api/admin/sql-mistake-examples`

### Phase 5: AI Prompt Planning

Prompts should be designed before connecting the AI model.

The main SQL generation prompt should include:

- System role.
- Database type.
- Output format rule.
- Read-only SQL rule.
- Forbidden SQL operations.
- Schema usage rule.
- Date filter rule.
- Limit rule.
- Clarification rule.

Example rules:

- Return only one SQL query.
- Use only `SELECT` or `WITH`.
- Do not generate `INSERT`, `UPDATE`, `DELETE`, `DROP`, or `ALTER`.
- Use only documented tables and columns.
- If the question is unclear, ask for clarification.

### Phase 6: AI SQL Generation Flow

The planned flow should be:

1. Receive user question.
2. Validate user question is report-related.
3. Detect report category.
4. Resolve date filters.
5. Load relevant schema.
6. Build AI prompt.
7. Generate SQL.
8. Validate SQL.
9. Retry if invalid.
10. Execute SQL if valid.
11. Return report.

## 8. Safety Planning

Safety is the most important part of this type of system.

### User Question Safety

Block questions that ask to:

- insert data
- update data
- delete data
- drop tables
- alter schema
- create users
- run stored procedures
- execute admin commands

### SQL Safety

Generated SQL must be checked for:

- Only `SELECT` or `WITH`.
- No multiple statements.
- No comments hiding unsafe SQL.
- No write/admin keywords.
- No unknown tables.
- No unknown columns.
- Safe row limits.

### Database Permission Safety

Use a read-only database user for report execution. Even if validation fails, the database user should not have permission to modify data.

## 9. Validation Planning

Use multiple validation layers:

### Layer 1: User Intent Validation

Checks the user question before AI generation.

### Layer 2: SQL Syntax and Keyword Validation

Checks whether generated SQL is read-only.

### Layer 3: Schema Validation

Checks tables and columns against known schema.

### Layer 4: AI Validator

Optionally use a second model to validate generated SQL.

### Layer 5: Database Execution Error Handling

If database rejects SQL, capture the error and retry with correction.

## 10. Retry Planning

Retry logic should be planned carefully.

Recommended retry flow:

1. AI generates first SQL.
2. Validator checks SQL.
3. If invalid, save failed SQL and reason.
4. Send failed SQL and reason back to AI.
5. AI regenerates corrected SQL.
6. Validate again.
7. Stop after a fixed number of retries.
8. Return a clear error if still invalid.

Do not allow infinite retries.

## 11. Learning System Planning

The system can improve over time by storing examples.

### Store Successful Attempts

Save:

- user question
- generated SQL
- final SQL
- execution status
- row count
- admin approval status

### Store Failed Attempts

Save:

- user question
- wrong SQL
- validator reason
- mistake type
- corrected SQL if available

### Gold Examples

Admin-approved successful SQL should become gold examples.

Future prompts can include similar gold examples to improve SQL generation.

## 12. Frontend Planning

The frontend should include:

- Question input box.
- Report category dropdown.
- Date filters.
- Generate button.
- Loading state.
- Error display.
- Report summary.
- Result table.
- Generated SQL toggle.
- Retry/validation status.
- Export button.

Admin frontend should include:

- AI attempt list.
- Attempt details.
- Final SQL preview.
- Execution status.
- Validator feedback.
- Approve/reject buttons.
- Mistake examples list.

## 13. Database Table Planning for App Metadata

Recommended application tables:

### `ai_sql_attempts`

Stores all AI report attempts.

Columns:

- `id`
- `user_question`
- `schema_snapshot`
- `generated_sql`
- `validator_status`
- `validator_feedback`
- `regenerated_sql`
- `final_sql`
- `execution_status`
- `execution_error`
- `result_row_count`
- `user_feedback_status`
- `admin_approved`
- `is_gold_example`
- `created_at`
- `updated_at`

### `sql_mistake_examples`

Stores invalid SQL examples.

Columns:

- `id`
- `query_attempt_id`
- `user_question`
- `wrong_sql`
- `validator_feedback`
- `validation_reason`
- `mistake_type`
- `corrected_sql`
- `final_correct_sql`
- `risk_level`
- `created_at`

## 14. Testing Plan

### Unit Tests

Test:

- user query safety
- SQL guard
- schema validator
- date resolver
- report category detection
- cache key generation

### Integration Tests

Test:

- report query API
- dry-run report generation
- SQL execution against test database
- schema refresh
- admin review flow

### AI Tests

Test with fixed questions:

- valid project report
- invalid dangerous request
- unknown table request
- top N report
- date-range report
- ambiguous question

### Frontend Tests

Test:

- report form submission
- loading state
- error display
- table rendering
- SQL toggle
- admin approval flow

## 15. Deployment Planning

Production setup should include:

- Backend server.
- Frontend deployment.
- Read-only database user.
- Secure environment variables.
- HTTPS.
- Authentication.
- Role-based access.
- Logs and monitoring.
- AI provider key management.
- Database backup.
- Error tracking.

## 16. Security Checklist

Before production:

- Use read-only DB credentials.
- Protect admin APIs.
- Add authentication.
- Add rate limiting.
- Block unsafe SQL.
- Block unsafe user intent.
- Log all generated SQL.
- Store AI attempts for audit.
- Avoid exposing secrets in frontend.
- Limit returned rows.
- Add query timeout.
- Review prompts for injection risks.

## 17. Production Improvement Checklist

Recommended improvements:

- Use a real SQL parser instead of regex-only validation.
- Add pagination.
- Add saved reports.
- Add scheduled reports.
- Add export to Excel/PDF.
- Add role-based report access.
- Add prompt versioning.
- Add model performance tracking.
- Add automated schema sync.
- Add CI/CD pipeline.
- Add automated test coverage.

## 18. Simple Explanation for Stakeholders

This system works like a translator.

The user asks a business question in English. The AI converts that question into SQL. Before running the SQL, the backend checks whether it is safe and whether it uses real database tables and columns. If the SQL is safe, it runs on the database and returns a report.

The AI does not directly control the database. The backend is the gatekeeper.

## 19. Recommended Build Order

Build the system in this order:

1. Database connection.
2. Schema reader.
3. Static schema catalog.
4. Basic report API.
5. SQL safety validator.
6. Built-in report templates.
7. AI SQL generation.
8. Schema validation.
9. Retry logic.
10. Frontend report screen.
11. Attempt logging.
12. Admin review screen.
13. Gold-example learning.
14. Export and production hardening.

## 20. Final Notes

An AI reporting system should never be planned as "AI directly talks to the database."

It should be planned as:

> User question -> AI-generated SQL -> backend validation -> safe execution -> report output

That architecture keeps the system useful, understandable, and safer for production.

