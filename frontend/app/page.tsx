"use client";

import {useEffect, useMemo, useState} from "react";
import {
  BarChart3,
  Bot,
  Boxes,
  CalendarCheck,
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
  User,
  Users
} from "lucide-react";
import {GeneratedReport, Health, getHealth, runReport} from "@/lib/api";

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

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Home() {
  const [question, setQuestion] = useState(examples[0]);
  const [month, setMonth] = useState("April");
  const [year, setYear] = useState("2026");
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [status, setStatus] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSql, setShowSql] = useState(true);

  useEffect(() => {
    getHealth().then(setStatus).catch(() => setStatus(null));
  }, []);

  const visibleRows = useMemo(() => report?.rows.slice(0, 100) ?? [], [report]);

  async function submit(nextQuestion = question) {
    setQuestion(nextQuestion);
    setLoading(true);
    setError("");
    try {
      const result = await runReport({
        question: nextQuestion,
        limit: 500,
        dry_run: false
      });
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
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
            {error && <div className="error">{error}</div>}

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
                    <p>{report.explanation}</p>
                  </div>
                  <span className="row-count">{report.row_count} rows</span>
                </div>

                {report.assumptions.length > 0 && (
                  <div className="assumptions">
                    {report.assumptions.map((item) => <span key={item}>Assumption: {item}</span>)}
                  </div>
                )}

                {visibleRows.length > 0 && (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>{report.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {report.columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <button className="sql-toggle" onClick={() => setShowSql((value) => !value)}>
                  {showSql ? "▼" : "▶"} Generated SQL
                </button>
                {showSql && <pre className="sql-box">{report.sql}</pre>}
              </>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
