"use client";

import {useEffect, useMemo, useState} from "react";
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
  Filter,
  HelpCircle,
  LayoutDashboard,
  Loader2,
  Menu,
  Search,
  Send,
  Settings,
  ThumbsDown,
  ThumbsUp,
  User,
  Users
} from "lucide-react";
import {ApiError, GeneratedReport, Health, RetryAttempt, getHealth, runReport, submitReportFeedback} from "@/lib/api";

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

const feedbackReasons = [
  "Result is useful",
  "Wrong table used",
  "Wrong column used",
  "Incorrect date range",
  "Missing filters",
  "Wrong aggregation",
  "Data looks incomplete",
  "Report format confusing",
  "SQL failed",
  "Other"
];

const numberFormatter = new Intl.NumberFormat("en-IN", {maximumFractionDigits: 2});
const dateFormatter = new Intl.DateTimeFormat("en-GB", {day: "2-digit", month: "short", year: "numeric"});

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
  const [feedbackRating, setFeedbackRating] = useState<"up" | "down" | null>(null);
  const [feedbackReason, setFeedbackReason] = useState("");
  const [feedbackComment, setFeedbackComment] = useState("");
  const [expectedResult, setExpectedResult] = useState("");
  const [correctedSql, setCorrectedSql] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackError, setFeedbackError] = useState("");

  useEffect(() => {
    getHealth().then(setStatus).catch(() => setStatus(null));
  }, []);

  const visibleRows = useMemo(() => report?.rows.slice(0, 100) ?? [], [report]);
  const summaryItems = useMemo(() => report ? buildSummaryItems(report) : [], [report]);

  async function submit(nextQuestion = question) {
    setQuestion(nextQuestion);
    setLoading(true);
    setError("");
    setErrorTitle("");
    setErrorSolution("");
    setErrorStatusCode(null);
    setRetryAttempts([]);
    setGeneratedAt(null);
    resetFeedback();
    try {
      const result = await runReport({
        question: nextQuestion,
        limit: 500,
        dry_run: false
      });
      setReport(result);
      setRetryAttempts(result.retry_attempts ?? []);
      setGeneratedAt(dateFormatter.format(new Date()));
      setShowSql(false);
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

  function resetFeedback() {
    setFeedbackRating(null);
    setFeedbackReason("");
    setFeedbackComment("");
    setExpectedResult("");
    setCorrectedSql("");
    setFeedbackMessage("");
    setFeedbackError("");
  }

  async function submitFeedback() {
    if (!report || !feedbackRating) return;
    setFeedbackSubmitting(true);
    setFeedbackMessage("");
    setFeedbackError("");
    try {
      const result = await submitReportFeedback({
        question: report.question,
        report_title: report.title,
        generated_sql: report.sql,
        rating: feedbackRating,
        reason: feedbackReason || null,
        comment: feedbackComment || null,
        expected_result: expectedResult || null,
        corrected_sql: correctedSql || null,
        retry_attempts: report.retry_attempts,
        warnings: report.warnings,
        row_count: report.row_count
      });
      setFeedbackMessage(`${result.message} Reference: ${result.id}`);
      setFeedbackError("");
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : "Unable to save feedback");
    } finally {
      setFeedbackSubmitting(false);
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
          <div className="nav-row"><Settings size={21} /><span>Settings</span></div>
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
            <span>Yogesh Tamhankar | Project Manager</span>
          </div>
        </header>

        <section className="content">
          <section className="filter-card">
            <div className="filter-grid">
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

              <div className="searchbar">
                <Search size={28} />
                <input value={question} onChange={(event) => setQuestion(event.target.value)} />
                <button onClick={() => submit()} disabled={loading}>
                  {loading ? <Loader2 className="spin" size={22} /> : <Send size={23} />}
                  <span>{loading ? "Generating" : "Generate"}</span>
                </button>
              </div>

              <div className="chips">
                {examples.map((example) => (
                  <button key={example} onClick={() => submit(example)}>{example}</button>
                ))}
              </div>
            </div>
          </section>

          <div className="report-actions">
            <label><input type="checkbox" defaultChecked /> Show CR Detailer</label>
            <label><input type="checkbox" defaultChecked /> Show CR Checker</label>
            <button><Download size={20} />Export PDF</button>
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
                {retryAttempts.map((attempt) => (
                  <div className={`retry-step ${attempt.status}`} key={`${attempt.attempt}-${attempt.status}`}>
                    <div>
                      <strong>Retry {attempt.attempt}</strong>
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

                <section className="feedback-panel">
                  <div className="feedback-header">
                    <div>
                      <h3>Report Feedback</h3>
                      <p>Help improve future SQL generation and report formatting.</p>
                    </div>
                    <div className="feedback-rating">
                      <button
                        className={feedbackRating === "up" ? "active" : ""}
                        onClick={() => setFeedbackRating("up")}
                        type="button"
                      >
                        <ThumbsUp size={18} /> Useful
                      </button>
                      <button
                        className={feedbackRating === "down" ? "active" : ""}
                        onClick={() => setFeedbackRating("down")}
                        type="button"
                      >
                        <ThumbsDown size={18} /> Needs Fix
                      </button>
                    </div>
                  </div>

                  <div className="feedback-grid">
                    <label>
                      <span>Reason</span>
                      <select value={feedbackReason} onChange={(event) => setFeedbackReason(event.target.value)}>
                        <option value="">Select reason</option>
                        {feedbackReasons.map((reason) => <option key={reason}>{reason}</option>)}
                      </select>
                    </label>
                    <label>
                      <span>Comment</span>
                      <textarea
                        value={feedbackComment}
                        onChange={(event) => setFeedbackComment(event.target.value)}
                        placeholder="What worked or what should change?"
                      />
                    </label>
                    <label>
                      <span>Expected result</span>
                      <textarea
                        value={expectedResult}
                        onChange={(event) => setExpectedResult(event.target.value)}
                        placeholder="Describe the report you expected."
                      />
                    </label>
                    <label>
                      <span>Correct SQL</span>
                      <textarea
                        value={correctedSql}
                        onChange={(event) => setCorrectedSql(event.target.value)}
                        placeholder="Optional: paste corrected SQL for review."
                      />
                    </label>
                  </div>

                  <div className="feedback-footer">
                    <button disabled={!feedbackRating || feedbackSubmitting} onClick={submitFeedback} type="button">
                      {feedbackSubmitting ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
                      Submit Feedback
                    </button>
                    {feedbackMessage && <span className="feedback-success">{feedbackMessage}</span>}
                    {feedbackError && <span className="feedback-error">{feedbackError}</span>}
                  </div>
                </section>
              </>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
