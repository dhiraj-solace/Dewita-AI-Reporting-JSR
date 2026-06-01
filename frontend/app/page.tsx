"use client";

import {useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {
  BarChart3,
  Bot,
  Boxes,
  CalendarCheck,
  ChevronDown,
  ChevronRight,
  CheckSquare,
  ClipboardList,
  Database,
  Download,
  Expand,
  FileSpreadsheet,
  FileText,
  Filter,
  HelpCircle,
  History,
  LayoutDashboard,
  Loader2,
  Menu,
  Search,
  Send,
  Settings,
  CalendarClock,
  User,
  Users
} from "lucide-react";
import {
  ApiError,
  GeneratedReport,
  Health,
  ReportCategory,
  RoleReportPermission,
  RetryAttempt,
  SavedReportSummary,
  getHealth,
  getSavedReport,
  listReportCategories,
  listReportPermissions,
  listSavedReports,
  runReport,
  savedReportExportUrl,
  shareSavedReport
} from "@/lib/api";

const monthOptions = ["January", "February", "March", "April", "May", "June"];
const examples = [
  "Show April 2026 revision summary by project and team leader",
  "Projects where actual revision hours are greater than assigned hours",
  "Week 5 report with totals grouped by project type",
  "Top team leaders by equivalent new tickets this year"
];

const navItems = [
  {label: "Dashboard", icon: LayoutDashboard},
  {label: "Project Management", icon: ClipboardList},
  {label: "Product Management", icon: Boxes},
  {label: "Timesheet Management", icon: CheckSquare},
  {label: "Report Management", icon: BarChart3, active: true}
];

const reports = [
  "Dai Week 5 Report",
  "Week 5 Report",
  "Daily Report",
  "Revision Report",
  "Markup Report",
  "Post Error Request Report",
  "Team Efficiency Report",
  "Individual Rating Report",
  "Employee Capacity Report",
  "Project Summary Report",
  "Employee Summary"
];

const stats = [
  ["View Projects", "36"],
  ["View Products", "20"],
  ["View ProjectType", "11"],
  ["View Error", "2912"],
  ["View E drawing Error", "1"],
  ["View Project Manager", "23"],
  ["View Team Leader", "19"],
  ["View Team Member", "57"],
  ["View All Member", "77"]
];

const numberFormatter = new Intl.NumberFormat("en-IN", {maximumFractionDigits: 2});
const dateFormatter = new Intl.DateTimeFormat("en-GB", {day: "2-digit", month: "short", year: "numeric"});
const sqlProviderOptions = [
  {label: "OpenRouter", value: "openrouter"},
  {label: "Local Qwen", value: "ollama"}
] as const;
type SqlGenerationProvider = (typeof sqlProviderOptions)[number]["value"];
const roleOptions = ["Super Admin", "HR", "Project Manager", "Team Leader", "Team Member"];

const fallbackReportCategories: ReportCategory[] = [
  {id: "auto", label: "Auto Detect"},
  {id: "custom", label: "Custom Report"},
  {id: "project", label: "Project Report"},
  {id: "task", label: "Task Report"},
  {id: "attendance", label: "Attendance Report"},
  {id: "timesheet", label: "Timesheet Report"},
  {id: "revision", label: "Revision / Change Request Report"},
  {id: "quality", label: "Bug / Post Error Report"},
  {id: "product", label: "Product / Manufacturing Report"},
  {id: "team_employee", label: "Team / Employee Report"},
  {id: "bsl", label: "BSL Report"},
  {id: "checklist", label: "Checklist Report"},
  {id: "markup", label: "Markup / Drawing Report"}
];

function humanizeColumn(column: string) {
  const knownLabels: Record<string, string> = {
    id: "ID",
    project_no: "Project No",
    project_name: "Project Name",
    employee_id: "Employee ID",
    team_leader: "Team Leader",
    team_leader_name: "Team Leader",
    revision_count: "Revision Count",
    total_revisions: "Total Revisions",
    avg_effective_percentage: "Avg Effective %",
    effective_percentage: "Effective %",
    actual_man_hrs_utilized: "Actual Man Hours",
    total_budgeted_man_hrs: "Budgeted Man Hours"
  };
  if (knownLabels[column]) return knownLabels[column];
  return column
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/\bId\b/g, "ID")
    .replace(/\bCr\b/g, "CR")
    .replace(/\bAvg\b/g, "Avg");
}

function isNumericValue(value: unknown) {
  return typeof value === "number" || (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value)));
}

function isDateValue(column: string, value: unknown) {
  return /(^|_)date$|_at$/.test(column) && typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value);
}

function formatCell(column: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (isDateValue(column, value)) {
    const date = new Date(String(value));
    return Number.isNaN(date.getTime()) ? String(value) : dateFormatter.format(date);
  }
  if (isNumericValue(value)) {
    const numericValue = Number(value);
    const normalizedColumn = column.toLowerCase();
    if (/percentage|percent|pct/.test(normalizedColumn)) return `${numberFormatter.format(numericValue)}%`;
    if (/hours|hrs|_hr$|_hrs$/.test(normalizedColumn)) return `${numberFormatter.format(numericValue)} hrs`;
    return numberFormatter.format(numericValue);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function cellClassName(column: string, value: unknown) {
  const classes = [];
  if (isNumericValue(value)) classes.push("numeric-cell");
  if (/status|state/.test(column.toLowerCase())) classes.push("status-cell");
  return classes.join(" ");
}

function reportStatusLabel(report: GeneratedReport) {
  const hasFailedAttempt = report.retry_attempts.some((attempt) => attempt.status === "failed");
  const usedFallback = report.retry_attempts.some((attempt) => attempt.attempt >= 3 && attempt.status === "success");
  if (usedFallback) return "Template Fallback";
  if (hasFailedAttempt) return "AI Repaired";
  return report.dry_run ? "Dry Run" : "AI Generated";
}

function friendlyRetryMessage(attempt: RetryAttempt) {
  if (attempt.message.startsWith("Validator ")) {
    return attempt.message.replace(/^Validator (failed|success):\s*/i, "");
  }
  if (attempt.status === "success" && attempt.attempt >= 3) {
    return "A safe built-in report was used after generated SQL could not be repaired.";
  }
  if (attempt.status === "success") {
    return attempt.attempt > 1 ? "The regenerated SQL passed validation and returned data." : "The generated SQL passed validation and returned data.";
  }
  const issue = attempt.schema_issue || attempt.message;
  if (issue.toLowerCase().includes("does not exist")) {
    return `The query referenced a schema field that is not available. ${issue}`;
  }
  return issue;
}

function validationSummary(attempts: RetryAttempt[]) {
  const validatorAttempts = attempts.filter((attempt) => attempt.message.startsWith("Validator "));
  if (validatorAttempts.length === 0) return "";
  const success = validatorAttempts.find((attempt) => attempt.status === "success");
  if (success) return `Validation passed on attempt ${success.attempt}.`;
  return `Validation stopped after ${validatorAttempts.length} attempts.`;
}

function buildSummaryItems(report: GeneratedReport) {
  const items = [
    {label: "Rows returned", value: numberFormatter.format(report.row_count)},
    {label: "Columns", value: numberFormatter.format(report.columns.length)},
    {label: "Report status", value: reportStatusLabel(report)}
  ];
  const numericColumns = report.columns.filter((column) => report.rows.some((row) => isNumericValue(row[column])));
  const priorityColumn = numericColumns.find((column) => /total|count|revision|hours|hrs|percentage|amount|budget/i.test(column));
  if (priorityColumn) {
    const values = report.rows.map((row) => Number(row[priorityColumn])).filter((value) => !Number.isNaN(value));
    const useAverage = /avg|average|percentage|percent|pct/i.test(priorityColumn);
    const calculated = useAverage
      ? values.reduce((total, value) => total + value, 0) / Math.max(values.length, 1)
      : values.reduce((total, value) => total + value, 0);
    items.push({
      label: `${useAverage ? "Average" : "Total"} ${humanizeColumn(priorityColumn)}`,
      value: formatCell(priorityColumn, calculated)
    });
  }
  return items.slice(0, 4);
}

export default function Home() {
  const [question, setQuestion] = useState(examples[0]);
  const [month, setMonth] = useState("April");
  const [year, setYear] = useState("2026");
  const [reportCategory, setReportCategory] = useState("auto");
  const [currentRole, setCurrentRole] = useState("Super Admin");
  const [reportCategories, setReportCategories] = useState<ReportCategory[]>(fallbackReportCategories);
  const [rolePermissions, setRolePermissions] = useState<RoleReportPermission[]>([]);
  const [sqlProvider, setSqlProvider] = useState<SqlGenerationProvider>("openrouter");
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [status, setStatus] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [errorTitle, setErrorTitle] = useState("");
  const [errorSolution, setErrorSolution] = useState("");
  const [errorStatusCode, setErrorStatusCode] = useState<number | null>(null);
  const [retryAttempts, setRetryAttempts] = useState<RetryAttempt[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [savedReports, setSavedReports] = useState<SavedReportSummary[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareEmail, setShareEmail] = useState("");
  const [shareMessage, setShareMessage] = useState("");
  const [shareFormats, setShareFormats] = useState<Array<"pdf" | "xlsx">>(["xlsx"]);
  const [shareSaving, setShareSaving] = useState(false);
  const [shareStatus, setShareStatus] = useState("");

  useEffect(() => {
    getHealth().then(setStatus).catch(() => setStatus(null));
    listReportCategories()
      .then((categories) => {
        if (categories.length > 0) setReportCategories(categories);
      })
      .catch(() => setReportCategories(fallbackReportCategories));
    listReportPermissions()
      .then((payload) => {
        if (payload.categories.length > 0) setReportCategories(payload.categories);
        setRolePermissions(payload.permissions);
      })
      .catch(() => setRolePermissions([]));
  }, []);

  useEffect(() => {
    refreshSavedReports();
    setReport(null);
  }, [currentRole]);

  const visibleRows = useMemo(() => report?.rows.slice(0, 100) ?? [], [report]);
  const summaryItems = useMemo(() => report ? buildSummaryItems(report) : [], [report]);
  const retrySummary = useMemo(() => validationSummary(retryAttempts), [retryAttempts]);
  const activeSavedReportId = report?.saved_report_id ?? null;
  const visibleReportCategories = useMemo(() => {
    const allowed = new Set(
      rolePermissions
        .filter((permission) => permission.role_name === currentRole && permission.can_create && permission.data_scope !== "none")
        .map((permission) => permission.report_category)
    );
    if (allowed.size === 0 && rolePermissions.length > 0) return [];
    const permitted = reportCategories.filter((category) => category.id !== "auto" && (allowed.size === 0 || allowed.has(category.id)));
    const autoCategory = reportCategories.find((category) => category.id === "auto") || {id: "auto", label: "Auto Detect"};
    return [autoCategory, ...permitted];
  }, [currentRole, reportCategories, rolePermissions]);

  useEffect(() => {
    if (visibleReportCategories.length === 0) return;
    if (reportCategory === "auto") return;
    if (!visibleReportCategories.some((category) => category.id === reportCategory)) {
      setReportCategory("auto");
    }
  }, [reportCategory, visibleReportCategories]);

  async function refreshSavedReports() {
    setSavedLoading(true);
    try {
      setSavedReports(await listSavedReports(currentRole));
    } catch {
      setSavedReports([]);
    } finally {
      setSavedLoading(false);
    }
  }

  async function loadSavedReport(reportId: string) {
    setLoading(true);
    setError("");
    setErrorTitle("");
    setErrorSolution("");
    setErrorStatusCode(null);
    try {
      const saved = await getSavedReport(reportId, currentRole);
      setReport(saved);
      setQuestion(saved.question);
      setRetryAttempts(saved.retry_attempts ?? []);
      setGeneratedAt(dateFormatter.format(new Date()));
      setShowSql(false);
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : "Unable to load saved report");
      setErrorTitle("Unable to load saved report");
    } finally {
      setLoading(false);
    }
  }

  function downloadSavedReport(format: "pdf" | "xlsx") {
    if (!activeSavedReportId) return;
    window.location.href = savedReportExportUrl(activeSavedReportId, format, currentRole);
  }

  function openShareModal() {
    if (!activeSavedReportId) return;
    setShareOpen(true);
    setShareStatus("");
  }

  function toggleShareFormat(format: "pdf" | "xlsx", checked: boolean) {
    setShareFormats((current) => {
      const next = new Set(current);
      if (checked) next.add(format);
      else next.delete(format);
      return Array.from(next);
    });
    setShareStatus("");
  }

  async function submitShare() {
    if (!activeSavedReportId) return;
    if (!shareEmail.trim()) {
      setShareStatus("Recipient email is required.");
      return;
    }
    if (shareFormats.length === 0) {
      setShareStatus("Select at least one format.");
      return;
    }
    setShareSaving(true);
    setShareStatus("");
    try {
      const result = await shareSavedReport(activeSavedReportId, {
        recipient_email: shareEmail.trim(),
        message: shareMessage.trim() || null,
        formats: shareFormats,
        current_user_role: currentRole
      });
      setShareStatus(result.message);
    } catch (err) {
      setShareStatus(err instanceof Error ? err.message : "Unable to share report");
    } finally {
      setShareSaving(false);
    }
  }

  async function submit(nextQuestion = question) {
    setQuestion(nextQuestion);
    setLoading(true);
    setError("");
    setErrorTitle("");
    setErrorSolution("");
    setErrorStatusCode(null);
    setRetryAttempts([]);
    setGeneratedAt(null);
    try {
      const result = await runReport({
        question: nextQuestion,
        report_category: reportCategory,
        current_user_role: currentRole,
        limit: 500,
        dry_run: false,
        sql_generation_provider: sqlProvider
      });
      setReport(result);
      setRetryAttempts(result.retry_attempts ?? []);
      setGeneratedAt(dateFormatter.format(new Date()));
      setShowSql(false);
      refreshSavedReports();
    } catch (err) {
      setReport(null);
      if (err instanceof ApiError) {
        setError(err.message);
        setErrorTitle(err.title);
        setErrorSolution(err.solution ?? "");
        setErrorStatusCode(err.statusCode ?? null);
        setRetryAttempts(err.retryAttempts);
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong");
        setErrorTitle("Unable to run report");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div>
            <strong>DEVITA</strong>
            <span>Engineering India Private Limited</span>
          </div>
        </div>

        <span className="menu-label">MENU</span>
        <nav className="main-nav">
          {navItems.map((item) => (
            <div className={item.active ? "nav-row active" : "nav-row"} key={item.label}>
              <item.icon size={21} />
              <span>{item.label}</span>
            </div>
          ))}
        </nav>

        <div className="report-nav">
          {reports.map((item) => (
            <button className={item === "Revision Report" ? "report-link active" : "report-link"} key={item}>
              <BarChart3 size={18} />
              <span>{item}</span>
            </button>
          ))}
        </div>

        <div className="utility-nav">
          <div className="nav-row"><Users size={21} /><span>Employee Summary</span></div>
          <div className="nav-row"><CheckSquare size={21} /><span>Checklist Management</span></div>
          <Link className="nav-row role-admin-link" href="/admin">
            <LayoutDashboard size={21} /><span>Admin Console</span>
          </Link>
          <Link className="nav-row role-admin-link" href="/admin/report-permissions">
            <Settings size={21} /><span>Report Permissions</span>
          </Link>
          <Link className="nav-row role-admin-link" href="/admin/scheduled-reports">
            <CalendarClock size={21} /><span>Scheduled Reports</span>
          </Link>
          <div className="nav-row help"><HelpCircle size={21} /><span>Help Section</span></div>
        </div>

        <div className="stats">
          {stats.map(([label, value]) => (
            <div className="stat" key={label}>
              <button>{label}</button>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </aside>

      <section className="page">
        <header className="topbar">
          <button className="icon-button" title="Menu"><Menu size={26} /></button>
          <div className="top-actions">
            <span className={status?.database_connected ? "connection online" : "connection"}>
              <Database size={17} /> {status?.database_connected ? "Live DB" : "DB pending"}
            </span>
            <button className="icon-button" title="Fullscreen"><Expand size={23} /></button>
            <User size={24} />
            <label className="role-switcher">
              <span>Active Role</span>
              <select value={currentRole} onChange={(event) => setCurrentRole(event.target.value)}>
                {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
          </div>
        </header>

        <section className="content">
          <section className="filter-card">
            <div className="filter-grid">
              <label>
                <span>Report Category</span>
                <select
                  value={visibleReportCategories.some((category) => category.id === reportCategory) ? reportCategory : ""}
                  onChange={(event) => setReportCategory(event.target.value)}
                  disabled={visibleReportCategories.length === 0}
                >
                  {visibleReportCategories.length === 0 && <option value="">No permitted reports</option>}
                  {visibleReportCategories.map((category) => (
                    <option key={category.id} value={category.id}>{category.label}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Month</span>
                <select value={month} onChange={(event) => setMonth(event.target.value)}>
                  {monthOptions.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label><span>Week</span><input value="5 Weeks Selected" readOnly /></label>
              <label><span>Year</span><input value={year} onChange={(event) => setYear(event.target.value)} /></label>
              <label><span>Project</span><select><option>Select Project</option></select></label>
              <label><span>Team Leader</span><select><option>Select Team Leader</option></select></label>
              <label><span>CR Detailer</span><select><option>Select CR Detailer</option></select></label>
              <label><span>CR Checker</span><select><option>Select CR Checker</option></select></label>
              <button className="filter-button"><Filter size={21} />Filter</button>
              <button className="clear-button">Clear</button>
            </div>

            <div className="assistant-panel">
              <div className="assistant-title">
                <Bot size={24} />
                <div>
                  <h1>AI Report Assistant</h1>
                  <p>Ask any complex report in natural language.</p>
                </div>
              </div>

              <div className="provider-switch" aria-label="SQL generation model">
                {sqlProviderOptions.map((option) => (
                  <button
                    className={sqlProvider === option.value ? "active" : ""}
                    key={option.value}
                    onClick={() => setSqlProvider(option.value)}
                    type="button"
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <div className="searchbar">
                <Search size={28} />
                <input value={question} onChange={(event) => setQuestion(event.target.value)} />
                <button onClick={() => submit()} disabled={loading || visibleReportCategories.length === 0}>
                  {loading ? <Loader2 className="spin" size={22} /> : <Send size={23} />}
                  <span>{loading ? "Generating" : "Generate"}</span>
                </button>
              </div>

              <div className="chips">
                {examples.map((example) => (
                  <button disabled={visibleReportCategories.length === 0} key={example} onClick={() => submit(example)}>{example}</button>
                ))}
              </div>
            </div>
          </section>

          <div className="report-actions">
            <label><input type="checkbox" defaultChecked /> Show CR Detailer</label>
            <label><input type="checkbox" defaultChecked /> Show CR Checker</label>
            <button disabled={!activeSavedReportId} onClick={() => downloadSavedReport("pdf")}>
              <FileText size={20} />Export PDF
            </button>
            <button disabled={!activeSavedReportId} onClick={() => downloadSavedReport("xlsx")}>
              <FileSpreadsheet size={20} />Export Excel
            </button>
            <button disabled={!activeSavedReportId} onClick={openShareModal}>
              <Send size={20} />Share
            </button>
          </div>

          <section className="result-card">
            {error && (
              <div className="error-card">
                <div className="error-card-header">
                  <strong>{errorTitle || "Unable to run report"}</strong>
                  {errorStatusCode && <span>HTTP {errorStatusCode}</span>}
                </div>
                <p>{error}</p>
                {errorSolution && (
                  <div className="error-solution">
                    <span>Suggested fix</span>
                    <p>{errorSolution}</p>
                  </div>
                )}
              </div>
            )}
            {retryAttempts.length > 0 && (
              <div className="retry-panel">
                {retrySummary && (
                  <div className="retry-summary">
                    <strong>Validation check</strong>
                    <span>{retrySummary}</span>
                  </div>
                )}
                {retryAttempts.map((attempt, index) => (
                  <div className={`retry-step ${attempt.status}`} key={`${attempt.attempt}-${attempt.status}-${index}`}>
                    <div>
                      <strong>{attempt.message.startsWith("Validator ") ? `Output ${attempt.attempt}` : `Retry ${attempt.attempt}`}</strong>
                      <span>{attempt.status}</span>
                    </div>
                    <p>{friendlyRetryMessage(attempt)}</p>
                  </div>
                ))}
              </div>
            )}

            {!report && !error && (
              <div className="empty-state">
                <Bot size={42} />
                <h2>Ask a report question to generate live SQL and data.</h2>
              </div>
            )}

            {report && (
              <>
                <div className="report-header">
                  <div>
                    <h2>{report.title}</h2>
                    <p>{report.question}</p>
                  </div>
                  <span className="row-count">{reportStatusLabel(report)}</span>
                </div>

                <div className="report-meta">
                  <span><CalendarCheck size={16} /> Generated {generatedAt || "just now"}</span>
                  <span><Database size={16} /> Live DB</span>
                  <span>{numberFormatter.format(report.row_count)} rows</span>
                  <span>{numberFormatter.format(report.retry_attempts.length)} attempts</span>
                  {report.attempt_id && <span>Attempt {report.attempt_id.slice(0, 8)}</span>}
                </div>

                <div className="summary-grid">
                  {summaryItems.map((item) => (
                    <div className="summary-item" key={item.label}>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="report-section">
                  <h3>Report Summary</h3>
                  <p>{report.explanation}</p>
                </div>

                {report.assumptions.length > 0 && (
                  <div className="notice-list assumptions">
                    {report.assumptions.map((item) => <span key={item}>Assumption: {item}</span>)}
                  </div>
                )}

                {report.warnings.length > 0 && (
                  <div className="notice-list warnings">
                    {report.warnings.map((item) => <span key={item}>Warning: {item}</span>)}
                  </div>
                )}

                {visibleRows.length > 0 && (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>{report.columns.map((column) => <th key={column}>{humanizeColumn(column)}</th>)}</tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {report.columns.map((column) => (
                              <td className={cellClassName(column, row[column])} key={column}>
                                {formatCell(column, row[column])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <button className="sql-toggle" onClick={() => setShowSql((value) => !value)}>
                  {showSql ? <ChevronDown size={18} /> : <ChevronRight size={18} />} Generated SQL
                </button>
                {showSql && <pre className="sql-box">{report.sql}</pre>}
              </>
            )}
          </section>

          <section className="saved-reports-panel">
            <div className="saved-reports-header">
              <div>
                <h2><History size={22} />Saved Reports</h2>
                <p>{savedLoading ? "Loading saved reports" : `${savedReports.length} recent reports`}</p>
              </div>
              <button onClick={refreshSavedReports} disabled={savedLoading}>
                {savedLoading ? <Loader2 className="spin" size={18} /> : <Download size={18} />}
                Refresh
              </button>
            </div>
            <div className="saved-report-list">
              {savedReports.length === 0 && <span className="saved-empty">No saved reports yet.</span>}
              {savedReports.map((item) => (
                <button
                  className={item.id === activeSavedReportId ? "saved-report-row active" : "saved-report-row"}
                  key={item.id}
                  onClick={() => loadSavedReport(item.id)}
                >
                  <strong>{item.title}</strong>
                  <span>{item.question}</span>
                  <em>{numberFormatter.format(item.row_count)} rows</em>
                </button>
              ))}
            </div>
          </section>

          {shareOpen && (
            <div className="share-modal-backdrop" role="presentation">
              <section className="share-modal" role="dialog" aria-modal="true" aria-label="Share saved report">
                <div className="share-modal-header">
                  <div>
                    <span>Saved Report</span>
                    <h2>Share Report</h2>
                  </div>
                  <button onClick={() => setShareOpen(false)} type="button">Close</button>
                </div>
                <label>
                  <span>Recipient Email</span>
                  <input value={shareEmail} onChange={(event) => setShareEmail(event.target.value)} placeholder="name@company.com" />
                </label>
                <label>
                  <span>Message</span>
                  <textarea value={shareMessage} onChange={(event) => setShareMessage(event.target.value)} placeholder="Optional message" />
                </label>
                <div className="share-format-row">
                  <label>
                    <input checked={shareFormats.includes("xlsx")} onChange={(event) => toggleShareFormat("xlsx", event.target.checked)} type="checkbox" />
                    <span>Excel</span>
                  </label>
                  <label>
                    <input checked={shareFormats.includes("pdf")} onChange={(event) => toggleShareFormat("pdf", event.target.checked)} type="checkbox" />
                    <span>PDF</span>
                  </label>
                </div>
                {shareStatus && <div className="share-status">{shareStatus}</div>}
                <div className="share-actions">
                  <button onClick={() => setShareOpen(false)} type="button">Cancel</button>
                  <button className="active" disabled={shareSaving} onClick={submitShare} type="button">
                    {shareSaving ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
                    {shareSaving ? "Sharing" : "Share Report"}
                  </button>
                </div>
              </section>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
