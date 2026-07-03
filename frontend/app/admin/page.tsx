"use client";

import {useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bot,
  CalendarClock,
  Database,
  FileClock,
  FileWarning,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  User,
  Users
} from "lucide-react";
import {
  AiSqlAttempt,
  Health,
  ReportAuditLog,
  ReportPermissionsMatrix,
  ScheduledReport,
  getHealth,
  listAiSqlAttempts,
  listReportAuditLogs,
  listReportPermissions,
  listScheduledReports
} from "@/lib/api";
import AdminGuard from "./AdminGuard";

type AdminModule = {
  key: string;
  title: string;
  description: string;
  href: string;
  icon: typeof Bot;
  metric: string;
  meta: string;
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function countSuccessful(attempts: AiSqlAttempt[]) {
  return attempts.filter((attempt) => (attempt.execution_status || "").toLowerCase() === "success").length;
}

function countActiveSchedules(schedules: ScheduledReport[]) {
  return schedules.filter((schedule) => schedule.is_active).length;
}

export default function AdminConsolePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [attempts, setAttempts] = useState<AiSqlAttempt[]>([]);
  const [permissions, setPermissions] = useState<ReportPermissionsMatrix | null>(null);
  const [schedules, setSchedules] = useState<ScheduledReport[]>([]);
  const [auditLogs, setAuditLogs] = useState<ReportAuditLog[]>([]);
  const [activeModuleKey, setActiveModuleKey] = useState("scheduled-reports");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [healthData, attemptData, permissionData, scheduleData, auditData] = await Promise.all([
        getHealth().catch(() => null),
        listAiSqlAttempts(false).catch(() => []),
        listReportPermissions().catch(() => null),
        listScheduledReports().catch(() => []),
        listReportAuditLogs(12).catch(() => [])
      ]);
      setHealth(healthData);
      setAttempts(attemptData);
      setPermissions(permissionData);
      setSchedules(scheduleData);
      setAuditLogs(auditData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load admin console");
    } finally {
      setLoading(false);
    }
  }

  const modules = useMemo<AdminModule[]>(() => [
    {
      key: "users",
      title: "Users",
      description: "Create application users, assign roles, and manage login access.",
      href: "/admin/users",
      icon: Users,
      metric: `${permissions?.roles.length ?? 0}`,
      meta: "login access"
    },
    {
      key: "ai-sql-attempts",
      title: "AI SQL Attempts",
      description: "Review generated SQL, validator feedback, timings, mistakes, and gold examples.",
      href: "/admin/ai-sql-attempts",
      icon: Bot,
      metric: `${attempts.length}`,
      meta: `${countSuccessful(attempts)} successful`
    },
    {
      key: "sql-mistakes",
      title: "SQL Mistakes",
      description: "Group repeated mistakes, inspect examples, and choose what feeds future context.",
      href: "/admin/sql-mistakes",
      icon: FileWarning,
      metric: `${attempts.filter((attempt) => attempt.execution_status === "failed").length}`,
      meta: "mistake review"
    },
    {
      key: "report-permissions",
      title: "Report Permissions",
      description: "Assign report categories, actions, and data scope to each business role.",
      href: "/admin/report-permissions",
      icon: ShieldCheck,
      metric: `${permissions?.roles.length ?? 0}`,
      meta: `${permissions?.categories.filter((category) => category.id !== "auto").length ?? 0} categories`
    },
    {
      key: "scheduled-reports",
      title: "Scheduled Reports",
      description: "Create automated reports, manage recipients, and run schedules as Super Admin.",
      href: "/admin/scheduled-reports",
      icon: CalendarClock,
      metric: `${countActiveSchedules(schedules)}`,
      meta: `${schedules.length} total schedules`
    }
  ], [attempts, permissions, schedules]);

  const activeModule = modules.find((module) => module.key === activeModuleKey) || modules[0];

  const nextSchedule = useMemo(
    () => schedules
      .filter((schedule) => schedule.is_active && schedule.next_run_at)
      .sort((a, b) => new Date(a.next_run_at || "").getTime() - new Date(b.next_run_at || "").getTime())[0],
    [schedules]
  );

  return (
    <AdminGuard>
    <main className="admin-portal-shell">
      <section className="page">
        <header className="topbar">
          <button className="icon-button" title="Menu"><Menu size={26} /></button>
          <div className="top-actions">
            <span className={health?.database_connected ? "connection online" : "connection"}>
              <Database size={17} /> {health?.database_connected ? "Live DB" : "DB pending"}
            </span>
            <Link href="/" className="admin-report-link">Reporting UI</Link>
            <Link href="/admin" className="admin-report-link"><LayoutDashboard size={16} /> Admin Console</Link>
            <button className="icon-button" onClick={load} disabled={loading} title="Refresh" type="button">
              <RefreshCw className={loading ? "spin" : ""} size={22} />
            </button>
            <User size={24} />
          </div>
        </header>

        <section className="content admin-console-content">
          <header className="admin-console-hero">
            <div>
              <span>Administration</span>
              <h1>Admin Console</h1>
              <p>Manage AI quality, report access, and scheduled delivery from one control surface.</p>
            </div>
          </header>

          {error && <div className="admin-error">{error}</div>}

          <section className="admin-console-status">
            <div>
              <span><Database size={18} /> Database</span>
              <strong>{health?.database_connected ? "Connected" : "Pending"}</strong>
              <p>{health?.database_configured ? "Connection settings found" : "Database settings missing"}</p>
            </div>
            <div>
              <span><Activity size={18} /> AI Pipeline</span>
              <strong>{health?.ai_enabled ? "Enabled" : "Disabled"}</strong>
              <p>{attempts.length} tracked SQL attempts</p>
            </div>
            <div>
              <span><FileClock size={18} /> Next Schedule</span>
              <strong>{nextSchedule?.name || "None queued"}</strong>
              <p>{nextSchedule ? formatDate(nextSchedule.next_run_at) : "No active schedule time available"}</p>
            </div>
          </section>

          <section className="admin-workbench">
            <aside className="admin-workbench-nav">
              <div className="attempt-list-header">
                <span>Admin Modules</span>
                <strong>{modules.length}</strong>
              </div>
              {modules.map((module) => (
                <button
                  className={activeModuleKey === module.key ? "admin-tool-row active" : "admin-tool-row"}
                  key={module.key}
                  onClick={() => setActiveModuleKey(module.key)}
                  type="button"
                >
                  <module.icon size={22} />
                  <span>
                    <strong>{module.title}</strong>
                    <small>{module.meta}</small>
                  </span>
                  <ArrowRight size={17} />
                </button>
              ))}
            </aside>

            <section className="admin-workbench-window">
              <div className="admin-workbench-header">
                <div>
                  <span>Workspace</span>
                  <h2>{activeModule.title}</h2>
                </div>
                <p>{activeModule.description}</p>
              </div>
              <iframe src={`${activeModule.href}?embedded=1`} title={activeModule.title} />
            </section>
          </section>

          <section className="admin-module-grid compact">
            {modules.map((module) => (
              <button
                className={activeModuleKey === module.key ? "admin-module-card active" : "admin-module-card"}
                key={module.key}
                onClick={() => setActiveModuleKey(module.key)}
                type="button"
              >
                <div>
                  <module.icon size={24} />
                  <span>{module.title}</span>
                </div>
                <p>{module.description}</p>
                <footer>
                  <strong>{module.metric}</strong>
                  <span>{module.meta}</span>
                  <ArrowRight size={18} />
                </footer>
              </button>
            ))}
          </section>

          <section className="admin-console-grid">
            <div className="admin-console-panel">
              <div className="admin-console-panel-header">
                <h2><SlidersHorizontal size={20} /> Permission Coverage</h2>
                <Link href="/admin/report-permissions">Open</Link>
              </div>
              <div className="admin-role-list">
                {(permissions?.roles || []).slice(0, 6).map((role) => {
                  const allowed = permissions?.permissions.filter(
                    (permission) => permission.role_name === role && permission.can_create && permission.data_scope !== "none"
                  ).length ?? 0;
                  return (
                    <div key={role}>
                      <span>{role}</span>
                      <strong>{allowed} categories</strong>
                    </div>
                  );
                })}
                {!permissions && <div className="attempt-empty">Permission matrix unavailable.</div>}
              </div>
            </div>

            <div className="admin-console-panel">
              <div className="admin-console-panel-header">
                <h2><CalendarClock size={20} /> Schedule Health</h2>
                <Link href="/admin/scheduled-reports">Open</Link>
              </div>
              <div className="admin-schedule-list">
                {schedules.slice(0, 5).map((schedule) => (
                  <div key={schedule.id}>
                    <span className={schedule.is_active ? "schedule-status active" : "schedule-status"}>{schedule.is_active ? "Active" : "Paused"}</span>
                    <strong>{schedule.name}</strong>
                    <small>{schedule.frequency} at {schedule.schedule_time} {" · "} next {formatDate(schedule.next_run_at)}</small>
                  </div>
                ))}
                {schedules.length === 0 && <div className="attempt-empty">No scheduled reports configured.</div>}
              </div>
            </div>

            <div className="admin-console-panel audit-panel">
              <div className="admin-console-panel-header">
                <h2><Activity size={20} /> Recent Audit Activity</h2>
              </div>
              <div className="admin-audit-list">
                {auditLogs.map((log) => (
                  <div key={log.id}>
                    <strong>{log.event_type}</strong>
                    <span>{log.actor_role || "System"} {" · "} {log.action || "recorded"}</span>
                    <small>{formatDate(log.created_at)}</small>
                  </div>
                ))}
                {auditLogs.length === 0 && <div className="attempt-empty">No audit activity found.</div>}
              </div>
            </div>
          </section>
        </section>
      </section>
    </main>
    </AdminGuard>
  );
}
