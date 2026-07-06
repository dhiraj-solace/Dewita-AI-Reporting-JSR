"use client";

import {useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {ArrowLeft, CheckCircle2, Database, Loader2, RefreshCw, ShieldCheck, XCircle} from "lucide-react";
import {
  SqlMistakeGroup,
  listSqlMistakeGroups,
  setSqlMistakeGroupContextUsage
} from "@/lib/api";
import AdminGuard from "../AdminGuard";

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function groupContextState(group: SqlMistakeGroup) {
  if (group.included_count === 0) return "excluded";
  if (group.included_count === group.occurrence_count) return "included";
  return "partial";
}

export default function SqlMistakesAdminPage() {
  const [groups, setGroups] = useState<SqlMistakeGroup[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  const selected = useMemo(
    () => groups.find((group) => group.group_key === selectedKey) || groups[0] || null,
    [groups, selectedKey]
  );

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await listSqlMistakeGroups();
      setGroups(data);
      setSelectedKey((current) => current && data.some((group) => group.group_key === current) ? current : data[0]?.group_key || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load SQL mistake groups");
    } finally {
      setLoading(false);
    }
  }

  async function setGroupUsage(group: SqlMistakeGroup, useInContext: boolean) {
    setUpdating(group.group_key);
    setError("");
    try {
      await setSqlMistakeGroupContextUsage(group.group_key, useInContext);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update mistake group");
    } finally {
      setUpdating("");
    }
  }

  return (
    <AdminGuard>
      <main className="admin-shell sql-mistakes-shell">
        <header className="admin-header">
          <div>
            <h1>SQL Mistakes</h1>
            <p>Evaluate repeated SQL mistakes and choose which patterns are used as future context.</p>
          </div>
          <div className="admin-actions">
            <Link href="/admin" className="admin-report-link"><ArrowLeft size={16} /> Admin Console</Link>
            <button onClick={load} disabled={loading} type="button">
              <RefreshCw className={loading ? "spin" : ""} size={18} /> Refresh
            </button>
          </div>
        </header>

        {error && <div className="admin-error">{error}</div>}

        <section className="sql-mistakes-layout">
          <aside className="sql-mistake-groups">
            <div className="attempt-list-header">
              <span>Grouped Mistakes</span>
              <strong>{groups.length}</strong>
            </div>
            {loading && <div className="attempt-empty"><Loader2 className="spin" size={18} /> Loading mistakes</div>}
            {!loading && groups.length === 0 && <div className="attempt-empty">No mistake examples yet.</div>}
            {groups.map((group) => {
              const state = groupContextState(group);
              return (
                <button
                  className={selected?.group_key === group.group_key ? "sql-mistake-group active" : "sql-mistake-group"}
                  key={group.group_key}
                  onClick={() => setSelectedKey(group.group_key)}
                  type="button"
                >
                  <span>
                    <strong>{group.mistake_type}</strong>
                    <small>{group.user_question}</small>
                  </span>
                  <em>{group.occurrence_count}x</em>
                  <i className={`context-chip ${state}`}>{state}</i>
                </button>
              );
            })}
          </aside>

          <section className="sql-mistake-detail">
            {!selected && !loading && <div className="attempt-empty">Select a mistake group.</div>}
            {selected && (
              <>
                <div className="sql-mistake-detail-header">
                  <div>
                    <span>{selected.mistake_type}</span>
                    <h2>{selected.user_question}</h2>
                    <p>{selected.reason || "No validator reason captured."}</p>
                  </div>
                  <div className="sql-mistake-actions">
                    <button disabled={updating === selected.group_key} onClick={() => setGroupUsage(selected, true)} type="button">
                      <CheckCircle2 size={17} /> Include group
                    </button>
                    <button disabled={updating === selected.group_key} onClick={() => setGroupUsage(selected, false)} type="button">
                      <XCircle size={17} /> Exclude group
                    </button>
                  </div>
                </div>

                <section className="sql-mistake-stats">
                  <div><span>Occurrences</span><strong>{selected.occurrence_count}</strong></div>
                  <div><span>In context</span><strong>{selected.included_count}</strong></div>
                  <div><span>Risk</span><strong>{selected.risk_level}</strong></div>
                  <div><span>Latest</span><strong>{formatDate(selected.latest_created_at)}</strong></div>
                </section>

                <section className="sql-mistake-examples">
                  {selected.examples.map((example) => (
                    <article className="sql-mistake-example" key={example.id}>
                      <header>
                        <span className={example.use_in_context ? "context-chip included" : "context-chip excluded"}>
                          {example.use_in_context ? "In context" : "Excluded"}
                        </span>
                        <small>
                          {example.validator_source || "backend"} · {example.validation_stage || "backend"} · {formatDate(example.created_at)}
                        </small>
                      </header>
                      <p>{example.validation_reason || example.validator_feedback || selected.reason || "-"}</p>
                      {(example.missing_table || example.missing_column) && (
                        <p>
                          Missing: {[example.missing_table, example.missing_column].filter(Boolean).join(".")}
                        </p>
                      )}
                      <details>
                        <summary><Database size={15} /> Wrong SQL</summary>
                        <pre>{example.wrong_sql || "-"}</pre>
                      </details>
                      {(example.corrected_sql || example.final_correct_sql) && (
                        <details>
                          <summary><ShieldCheck size={15} /> Correct SQL</summary>
                          <pre>{example.corrected_sql || example.final_correct_sql}</pre>
                        </details>
                      )}
                    </article>
                  ))}
                </section>
              </>
            )}
          </section>
        </section>
      </main>
    </AdminGuard>
  );
}
