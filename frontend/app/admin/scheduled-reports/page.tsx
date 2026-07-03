"use client";

import {useEffect, useMemo, useState} from "react";
import {CalendarClock, Mail, Play, RefreshCw, Save, ToggleLeft, ToggleRight} from "lucide-react";
import {
  ReportCategory,
  ScheduledReport,
  ScheduledReportPayload,
  ScheduledReportRun,
  createScheduledReport,
  listReportCategories,
  listReportPermissions,
  listScheduledReportRuns,
  listScheduledReports,
  runScheduledReportNow,
  setScheduledReportStatus,
  updateScheduledReport
} from "@/lib/api";
import AdminGuard from "../AdminGuard";

const fallbackCategories: ReportCategory[] = [
  {id: "custom", label: "Custom Report"},
  {id: "project", label: "Project Report"},
  {id: "task", label: "Task Report"},
  {id: "attendance", label: "Attendance Report"},
  {id: "timesheet", label: "Timesheet Report"},
  {id: "revision", label: "Revision / Change Request Report"},
  {id: "quality", label: "Bug / Post Error Report"}
];

const emptyForm: ScheduledReportPayload = {
  name: "",
  report_category: "custom",
  question: "",
  frequency: "daily",
  schedule_time: "09:00",
  timezone: "Asia/Calcutta",
  filters: {date_preset: "current_month"},
  recipients: {emails: [], roles: [], delivery: ["saved_report"]},
  current_user_role: "Super Admin",
  sql_generation_provider: "openrouter",
  limit: 500,
  dry_run: false,
  export_formats: ["xlsx"],
  execution_settings: {},
  is_active: true
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function listFromText(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function textFromList(value: unknown) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function scheduleNameFrom(category: string, frequency: string, categories: ReportCategory[]) {
  const label = categories.find((item) => item.id === category)?.label || "Report";
  return `${label} ${frequency} schedule`;
}

function toForm(schedule: ScheduledReport): ScheduledReportPayload {
  return {
    name: schedule.name,
    report_category: schedule.report_category,
    question: schedule.question,
    frequency: schedule.frequency,
    schedule_time: schedule.schedule_time,
    timezone: schedule.timezone,
    filters: schedule.filters || {},
    recipients: schedule.recipients || {},
    current_user_role: schedule.current_user_role,
    sql_generation_provider: schedule.sql_generation_provider || "openrouter",
    limit: schedule.limit,
    dry_run: schedule.dry_run,
    export_formats: schedule.export_formats || [],
    execution_settings: schedule.execution_settings || {},
    is_active: schedule.is_active
  };
}

export default function ScheduledReportsAdminPage() {
  const [embedded, setEmbedded] = useState(false);
  const [schedules, setSchedules] = useState<ScheduledReport[]>([]);
  const [runs, setRuns] = useState<ScheduledReportRun[]>([]);
  const [categories, setCategories] = useState<ReportCategory[]>(fallbackCategories);
  const [roles, setRoles] = useState<string[]>(["Super Admin", "HR", "Project Manager", "Team Leader", "Team Member"]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ScheduledReportPayload>(emptyForm);
  const [emails, setEmails] = useState("");
  const [recipientRoles, setRecipientRoles] = useState("");
  const [datePreset, setDatePreset] = useState("current_month");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selected = useMemo(
    () => schedules.find((schedule) => schedule.id === selectedId) || null,
    [schedules, selectedId]
  );

  useEffect(() => {
    setEmbedded(new URLSearchParams(window.location.search).get("embedded") === "1");
  }, []);

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setRuns([]);
      return;
    }
    listScheduledReportRuns(selectedId).then(setRuns).catch(() => setRuns([]));
  }, [selectedId]);

  async function load() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const [scheduleData, categoryData, permissionData] = await Promise.all([
        listScheduledReports(),
        listReportCategories().catch(() => fallbackCategories),
        listReportPermissions().catch(() => null)
      ]);
      setSchedules(scheduleData);
      setCategories(categoryData.filter((category) => category.id !== "auto"));
      if (permissionData?.roles?.length) setRoles(permissionData.roles);
      const first = scheduleData[0] || null;
      setSelectedId(first?.id || null);
      if (first) hydrateForm(first);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load scheduled reports");
    } finally {
      setLoading(false);
    }
  }

  function hydrateForm(schedule: ScheduledReport) {
    const next = toForm(schedule);
    setForm(next);
    setDatePreset(String(next.filters.date_preset || ""));
    setEmails(textFromList(next.recipients.emails));
    setRecipientRoles(textFromList(next.recipients.roles));
  }

  function newSchedule() {
    setSelectedId(null);
    setForm(emptyForm);
    setDatePreset("current_month");
    setEmails("");
    setRecipientRoles("");
    setRuns([]);
    setMessage("");
  }

  function updateField<K extends keyof ScheduledReportPayload>(key: K, value: ScheduledReportPayload[K]) {
    setForm((current) => ({...current, [key]: value}));
    setMessage("");
  }

  function toggleExportFormat(format: string, checked: boolean) {
    setForm((current) => {
      const formats = new Set(current.export_formats || []);
      if (checked) {
        formats.add(format);
      } else {
        formats.delete(format);
      }
      return {...current, export_formats: Array.from(formats)};
    });
    setMessage("");
  }

  function payload(): ScheduledReportPayload {
    const recipientEmails = listFromText(emails);
    const scheduleName = form.name.trim() || scheduleNameFrom(form.report_category, form.frequency, categories);
    return {
      ...form,
      name: scheduleName,
      question: form.question.trim(),
      export_formats: form.export_formats.length ? form.export_formats : ["xlsx"],
      filters: {
        ...form.filters,
        date_preset: datePreset || undefined
      },
      recipients: {
        emails: recipientEmails,
        roles: listFromText(recipientRoles),
        delivery: recipientEmails.length ? ["saved_report", "email"] : ["saved_report"]
      }
    };
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const body = payload();
      const saved = selectedId
        ? await updateScheduledReport(selectedId, body)
        : await createScheduledReport(body);
      setMessage(selectedId ? "Schedule updated." : "Schedule created.");
      setSelectedId(saved.id);
      hydrateForm(saved);
      setSchedules((items) => {
        const exists = items.some((item) => item.id === saved.id);
        return exists ? items.map((item) => item.id === saved.id ? saved : item) : [saved, ...items];
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save schedule");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(schedule: ScheduledReport) {
    setError("");
    try {
      const updated = await setScheduledReportStatus(schedule.id, !schedule.is_active);
      setSchedules((items) => items.map((item) => item.id === updated.id ? updated : item));
      if (selectedId === updated.id) {
        setForm(toForm(updated));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update schedule status");
    }
  }

  async function runNow(schedule: ScheduledReport) {
    setRunning(schedule.id);
    setError("");
    try {
      await runScheduledReportNow(schedule.id);
      setMessage("Schedule run completed.");
      const [updatedSchedules, updatedRuns] = await Promise.all([
        listScheduledReports(),
        listScheduledReportRuns(schedule.id)
      ]);
      setSchedules(updatedSchedules);
      setRuns(updatedRuns);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run schedule");
    } finally {
      setRunning("");
    }
  }

  return (
    <AdminGuard>
    <main className={embedded ? "admin-shell schedule-shell embedded-admin-shell" : "admin-shell schedule-shell"}>
      <header className="admin-header">
        <div>
          <h1>Scheduled Reports</h1>
          <p>Super Admin can create, run, and email scheduled report jobs.</p>
        </div>
        <div className="admin-actions">
          <button onClick={newSchedule} type="button">New Schedule</button>
          <button onClick={load} disabled={loading || saving} type="button">
            <RefreshCw size={18} /> Refresh
          </button>
          <button className="active" onClick={save} disabled={saving} type="button">
            <Save size={18} /> {saving ? "Saving" : "Save"}
          </button>
        </div>
      </header>

      {error && <div className="admin-error">{error}</div>}
      {message && <div className="admin-success">{message}</div>}

      <section className="schedule-layout">
        <aside className="schedule-list">
          <div className="attempt-list-header">
            <span>Schedules</span>
            <strong>{schedules.length}</strong>
          </div>
          {loading && <div className="attempt-empty">Loading schedules...</div>}
          {!loading && schedules.length === 0 && <div className="attempt-empty">No schedules yet.</div>}
          {schedules.map((schedule) => (
            <button
              className={selectedId === schedule.id ? "schedule-row active" : "schedule-row"}
              key={schedule.id}
              onClick={() => {
                setSelectedId(schedule.id);
                hydrateForm(schedule);
              }}
              type="button"
            >
              <div>
                <strong>{schedule.name}</strong>
                <span className={schedule.is_active ? "schedule-status active" : "schedule-status"}>{schedule.is_active ? "Active" : "Paused"}</span>
              </div>
              <small>{schedule.report_category} • {schedule.frequency} at {schedule.schedule_time}</small>
              <small>Next: {formatDate(schedule.next_run_at)}</small>
              {schedule.last_status && <em>{schedule.last_status}</em>}
            </button>
          ))}
        </aside>

        <section className="schedule-editor">
          <div className="schedule-editor-header">
            <div>
              <span>{selectedId ? "Edit Schedule" : "New Schedule"}</span>
              <h2>{form.name || "Untitled schedule"}</h2>
            </div>
            {selected && (
              <div className="schedule-toolbar">
                <button onClick={() => toggle(selected)} type="button">
                  {selected.is_active ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                  {selected.is_active ? "Disable" : "Enable"}
                </button>
                <button onClick={() => runNow(selected)} disabled={running === selected.id} type="button">
                  <Play size={18} /> {running === selected.id ? "Running" : "Run Now"}
                </button>
              </div>
            )}
          </div>

          <div className="schedule-form">
            <label>
              <span>Name</span>
              <input value={form.name} onChange={(event) => updateField("name", event.target.value)} />
            </label>
            <label>
              <span>Report Category</span>
              <select value={form.report_category} onChange={(event) => updateField("report_category", event.target.value)}>
                {categories.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}
              </select>
            </label>
            <label>
              <span>Frequency</span>
              <select value={form.frequency} onChange={(event) => updateField("frequency", event.target.value as ScheduledReportPayload["frequency"])}>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </label>
            <label>
              <span>Schedule Time</span>
              <input type="time" value={form.schedule_time} onChange={(event) => updateField("schedule_time", event.target.value)} />
            </label>
            <label>
              <span>Run As Role</span>
              <select value={form.current_user_role} onChange={(event) => updateField("current_user_role", event.target.value)}>
                {roles.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
            <label>
              <span>Date Preset</span>
              <select value={datePreset} onChange={(event) => setDatePreset(event.target.value)}>
                <option value="">None</option>
                <option value="today">Today</option>
                <option value="yesterday">Yesterday</option>
                <option value="current_week">Current Week</option>
                <option value="previous_week">Previous Week</option>
                <option value="current_month">Current Month</option>
                <option value="previous_month">Previous Month</option>
              </select>
              <small className="schedule-help">Dynamic date range resolved when the schedule runs.</small>
            </label>
            <label>
              <span>Provider</span>
              <select value={form.sql_generation_provider || "openrouter"} onChange={(event) => updateField("sql_generation_provider", event.target.value as ScheduledReportPayload["sql_generation_provider"])}>
                <option value="openrouter">OpenRouter</option>
                <option value="ollama">Local Qwen</option>
                <option value="gemini">Gemini</option>
                <option value="openai">OpenAI</option>
              </select>
            </label>
            <label>
              <span>Limit</span>
              <input type="number" min={1} max={1000} value={form.limit} onChange={(event) => updateField("limit", Number(event.target.value))} />
            </label>
            <label className="schedule-wide">
              <span>Question</span>
              <textarea value={form.question} onChange={(event) => updateField("question", event.target.value)} />
            </label>
            <label>
              <span>Recipient Emails</span>
              <input value={emails} onChange={(event) => setEmails(event.target.value)} placeholder="email@company.com, second@company.com" />
            </label>
            <label>
              <span>Recipient Roles</span>
              <input value={recipientRoles} onChange={(event) => setRecipientRoles(event.target.value)} placeholder="HR, Super Admin" />
            </label>
            <div className="schedule-format-group">
              <span><Mail size={16} /> Email Attachments</span>
              <label className="schedule-check inline">
                <input
                  checked={(form.export_formats || []).includes("xlsx")}
                  onChange={(event) => toggleExportFormat("xlsx", event.target.checked)}
                  type="checkbox"
                />
                <span>Excel</span>
              </label>
              <label className="schedule-check inline">
                <input
                  checked={(form.export_formats || []).includes("pdf")}
                  onChange={(event) => toggleExportFormat("pdf", event.target.checked)}
                  type="checkbox"
                />
                <span>PDF</span>
              </label>
            </div>
            <label className="schedule-check">
              <input checked={form.is_active} onChange={(event) => updateField("is_active", event.target.checked)} type="checkbox" />
              <span>Schedule active</span>
            </label>
          </div>

          <section className="schedule-runs">
            <div className="schedule-runs-header">
              <h3><CalendarClock size={18} /> Run History</h3>
              <span>{runs.length} runs</span>
            </div>
            {runs.length === 0 && <div className="attempt-empty">No runs yet. Use Run Now to verify this schedule.</div>}
            {runs.map((run) => (
              <article className={run.status === "success" ? "run-row success" : run.status === "failed" ? "run-row failed" : "run-row"} key={run.id}>
                <div>
                  <strong>{run.status}</strong>
                  <span>{formatDate(run.started_at)} → {formatDate(run.finished_at)}</span>
                </div>
                <p>{run.error_message || `${run.generated_row_count ?? 0} rows generated`}</p>
                {run.saved_report_id && <small>Saved report: {run.saved_report_id.slice(0, 8)}</small>}
              </article>
            ))}
          </section>
        </section>
      </section>
    </main>
    </AdminGuard>
  );
}
