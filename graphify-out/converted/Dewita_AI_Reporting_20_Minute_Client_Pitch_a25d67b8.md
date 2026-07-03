<!-- converted from Dewita_AI_Reporting_20_Minute_Client_Pitch.docx -->

Dewita AI Reporting
20-Minute Client Pitch and Demo Guide

# 1. Opening Positioning
One-line pitch: Dewita AI Reporting is an AI-powered reporting layer that lets business users ask questions in plain English and receive safe SQL-backed reports from the company database.
Client framing: This is not a chatbot sitting outside the system. It is a controlled reporting workflow with permissions, validation, saved reports, audit logs, scheduled generation, and email delivery.
- Start with the pain: teams spend time asking developers or analysts for repeated database reports.
- Position the product as a reporting accelerator, not a replacement for governance.
- Mention that the current build already has admin controls, role-based report permissions, saved report sharing, and scheduled report automation.
# 2. 20-Minute Meeting Flow
# 3. Demo Script
## Demo Step 1 - Main Reporting Page
- Select a role, for example HR or Project Manager, to show that report access can change by role.
- Ask a simple business question such as: Show April 2026 revision summary by project and team leader.
- Run the report and point out the generated table, SQL visibility, date filters, export option, save report, and sharing flow.
- Explain that the AI proposes SQL, but backend validation decides whether it is safe to run.
## Demo Step 2 - Role-Based Report Permissions
- Open Admin Console and choose Report Permissions.
- Show report categories and actions: View, Create, Export, Save, View Saved.
- Explain that Admin can assign which role can access which report type.
- Use a simple example: HR can access attendance reports; Project Manager can access project and task reports; Employee can access only self-related reports.
## Demo Step 3 - AI SQL Attempts
- Show AI SQL Attempts for transparency into model-generated SQL.
- Explain performance tracking: provider, model, generation time, validator time, SQL execution time, total time, and status.
- Show that approved good SQL can become a gold example to improve future generations.
- Mention failed SQL/mistake examples are stored so the prompt can avoid repeating known mistakes.
## Demo Step 4 - Scheduled Reports
- Show Scheduled Reports inside Admin Console.
- Explain Super Admin-only access for schedule creation and manual run.
- Show report type, frequency, schedule time, date preset, provider, recipient emails, PDF/Excel attachments, active/inactive status, and run history.
- Explain that dynamic date presets like current month are resolved at runtime, so the same schedule works every month without code changes.
# 4. Feature-to-Value Talking Points
# 5. What to Avoid Saying
- Do not say the AI can run any SQL. Say it is restricted to safe read-only reporting queries.
- Do not promise final enterprise security until authentication, production deployment, and client-specific policies are confirmed.
- Do not focus too much on model names first. Start with business value, then explain models only if asked.
- Do not demo only the chatbot flow. Show admin governance, permissions, schedules, and audit logs because those make it client-ready.
# 6. Client Questions and Suggested Answers
# 7. Pilot Proposal
Recommended pilot scope: Start with 5-10 high-value reports, 3-5 user roles, saved report sharing, admin permission setup, and 2-3 scheduled reports. Keep the pilot focused on proving speed, accuracy, governance, and adoption.
# 8. Closing Script
- What we showed today is a working AI reporting foundation, not just a concept.
- The strongest value is combining natural-language reporting with admin control, permissions, audit logs, sharing, and scheduled automation.
- For the next step, we suggest a short pilot using your actual reporting examples and role structure so we can measure accuracy and time saved.
| Meeting goal
Show that Dewita AI Reporting turns natural-language business questions into safe, role-aware, shareable reports with admin control, scheduling, auditability, and production-ready extension points. |
| --- |
| Audience | Best message | Expected outcome |
| --- | --- | --- |
| New client, operations/head of delivery/management | Less manual reporting, faster decisions, controlled AI usage | Client understands the value and agrees to a pilot or discovery workshop |
| Time | Topic | What to say/show | Outcome |
| --- | --- | --- | --- |
| 0-2 min | Context | Explain the reporting pain: manual SQL, repeated Excel exports, slow response time. | Client agrees with the problem. |
| 2-5 min | Solution overview | Show main reporting screen and explain natural-language to validated SQL to report table. | Client sees the system direction. |
| 5-10 min | Live report demo | Ask a business question, run report, show generated SQL, table output, save/export/share options. | Client sees working value. |
| 10-13 min | Admin governance | Show Admin Console: AI SQL attempts, report permissions, scheduled reports. | Client sees control and trust layer. |
| 13-16 min | Automation | Show scheduled reports: daily/weekly/monthly, recipients, PDF/Excel attachments, run history. | Client sees operational automation. |
| 16-18 min | Security and access | Explain role-based permissions, audit logs, Super Admin controls, read-only SQL validation. | Client sees production thinking. |
| 18-20 min | Close | Summarize value, propose pilot scope, ask for sample reports and DB access/discovery. | Client has a clear next step. |
| Speaking line
The important part is not only that AI writes SQL. The important part is that we validate, log, control, save, share, and schedule the report like a real business system. |
| --- |
| Feature | Client value | How to explain it |
| --- | --- | --- |
| Natural-language reports | Less dependency on SQL developers for routine reports | Business users ask questions directly in the reporting UI. |
| Read-only SQL validation | Safer AI usage | Only SELECT/CTE style reporting queries are allowed; dangerous actions are blocked. |
| Role-based permissions | Controlled access | Admin decides which roles can create, view, save, export, and open saved reports. |
| Saved report sharing | Faster collaboration | Users can share saved reports by email with PDF/Excel attachments when SMTP is configured. |
| Scheduled reports | Automated delivery | Super Admin can create daily, weekly, or monthly reports without manual action. |
| Audit logging | Governance and traceability | Report saves, shares, permission changes, and schedule runs are recorded. |
| Model performance tracking | Operational visibility | Admin can review model/provider behavior and timing from the AI SQL attempts screen. |
| Question | Short answer |
| --- | --- |
| Can this connect to our database? | Yes. The backend connects to MySQL now, and the schema/catalog layer can be adapted to the client's database structure. |
| Is it safe if AI writes SQL? | The AI only proposes SQL. The backend validates read-only intent, SQL safety, schema references, role permissions, and execution limits before running. |
| Can managers get reports automatically? | Yes. Super Admin can configure daily, weekly, or monthly schedules with filters, recipients, and PDF/Excel email attachments. |
| Can we restrict reports by department or role? | Yes. The current module supports Admin-assigned report permissions by role and action. |
| Which models are used? | OpenRouter is used for SQL generation and intent detection; local Ollama models can also be used, including qwen2.5-coder:3b and smollm for validation. |
| What is needed for a pilot? | A sample database/schema, 5-10 priority reports, role list, access rules, SMTP details if email delivery is required, and acceptance criteria. |
| Pilot item | What client provides | What we deliver |
| --- | --- | --- |
| Database discovery | Read-only DB access or schema export | Schema catalog and table mapping |
| Report catalog | Priority report examples | Configured report categories and prompt examples |
| Roles and access | Role list and permission rules | Admin-managed permission matrix |
| Email delivery | SMTP credentials/app password | Report sharing and scheduled report emails |
| Acceptance | Expected outputs for sample questions | Tested reports and demo-ready flow |
| Final ask
Can you share 5 reports your team creates repeatedly, the roles who should access them, and whether reports need to be emailed daily, weekly, or monthly? |
| --- |