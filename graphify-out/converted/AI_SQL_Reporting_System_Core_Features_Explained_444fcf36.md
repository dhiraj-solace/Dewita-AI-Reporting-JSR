<!-- converted from AI_SQL_Reporting_System_Core_Features_Explained.docx -->

AI-Powered Report Generation System
A secure AI reporting platform that turns plain-English questions into validated SQL reports, with role permissions, saved reports, sharing/export, scheduled delivery, admin review, and learning from past attempts.
For a live demonstration, please reach out to the project team.
| Core Reporting Features
• Natural-language report input Users type normal business questions instead of writing SQL.
• Report category selection / auto-detect Users can choose a report type, or the system can classify the question automatically.
• Database schema reading The backend reads live/cached MySQL schema so AI uses real tables and columns.
• AI SQL generation The system generates SELECT SQL using schema context, examples, and report intent.
• Local Qwen / Ollama option Reports can be generated with a local Qwen model through Ollama when cloud AI is not preferred.
• Multiple provider support OpenRouter, Gemini, OpenAI, and Ollama can be selected/configured for SQL generation.
• Reusable report templates Common reports can use predefined SQL templates for faster and more reliable output.
• Generated SQL preview Users/admins can inspect the SQL behind every generated report.
• Report table display Results are returned as structured columns and rows for quick review in the UI.
• Error and retry handling Invalid output triggers validation feedback and regeneration instead of silent failure.
Safety & Validation
• SQL safety validation Blocks write operations and unsafe commands such as delete, update, drop, alter, and truncate.
• Schema validation Checks generated SQL against approved schema so unknown tables/columns are rejected.
• Read-only query execution Reports run through a controlled read-only execution path before results are shown.
• Storage of AI attempts Successful and failed SQL attempts are stored for review, audit, and improvement.
• Model/provider performance tracking Tracks provider, model, generation time, validation time, execution time, and total time.
Admin & Permissions
• Admin review dashboard Admins can review attempts, generated SQL, validator feedback, execution status, and result previews.
• Report permission management Admins map roles to report categories and actions such as view, create, save, export, and view saved.
• Role-based category access Users only see or run report categories allowed for their active role.
• Saved report access rules Saved reports are filtered by creator role, report category, and permission settings.
• Audit logging Saved-report events and permission changes are logged for traceability. | Saved Reports, Sharing & Export
• Saved reports Generated reports can be saved with title, question, category, role, SQL, rows, and metadata.
• Shared report delivery Saved reports can be shared to recipients with an optional message and selected attachment formats.
• Export options Reports can be exported as Excel/PDF, with CSV-style tabular data support in the report workflow.
• Saved report reopening Authorized users can reopen previous report outputs without regenerating the SQL.
• Export permission checks The backend checks role/category permissions before allowing saved-report export.
Scheduled Reports
• Scheduled auto-generation Daily, weekly, and monthly reports can run automatically from saved schedule settings.
• Super Admin schedule control Only Super Admin can create, edit, enable/disable, and manually run schedules.
• Manual Run Now Admins can trigger a schedule immediately to verify output and delivery.
• Dynamic date presets Schedules can use current/previous month or week so dates update automatically.
• Email notifications Scheduled reports can email recipients with PDF/Excel attachments when SMTP is configured.
• Run history Every schedule run stores status, row count, errors, saved report ID, and timestamps.
Learning & Improvement
• Gold examples Admin-approved successful SQL attempts become reusable examples for similar future questions.
• Mistake examples Rejected SQL and validator feedback are stored so the AI can avoid repeated mistakes.
• Vector search / RAG Similar approved examples are retrieved and injected into future prompts.
• Validator feedback loop Failed SQL receives specific feedback and can be regenerated with corrections.
Business Value
The platform gives teams faster self-service reporting while admins keep control over data access, generated SQL quality, saved reports, exports, scheduled delivery, and operational audit history. |
| --- | --- |