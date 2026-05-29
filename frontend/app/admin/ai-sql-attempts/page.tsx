"use client";

import {useEffect, useMemo, useState} from "react";
import {CheckCircle2, Database, RefreshCw, ShieldCheck, XCircle} from "lucide-react";
import {
  AiSqlAttempt,
  AiSqlAttemptEvent,
  AiSqlAttemptPreview,
  SqlMistakeExample,
  listAiSqlAttemptEvents,
  listAiSqlAttempts,
  listSqlMistakeExamples,
  previewAiSqlAttempt,
  reviewAiSqlAttempt
} from "@/lib/api";

function shortId(id: string) {
  return id.slice(0, 8);
}

function statusClass(value?: string | null) {
  if (!value) return "muted";
  return value.toLowerCase() === "success" ? "success" : value.toLowerCase() === "failed" ? "failed" : "muted";
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function compactSql(value?: string | null) {
  if (!value) return "-";
  return value.length > 140 ? `${value.slice(0, 139)}.` : value;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatMs(value?: number | null) {
  if (value === null || value === undefined) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

function countByStatus(attempts: AiSqlAttempt[], status: string) {
  return attempts.filter((attempt) => (attempt.execution_status || "pending").toLowerCase() === status).length;
}

export default function AiSqlAttemptsAdminPage() {
  const [embedded, setEmbedded] = useState(false);
  const [attempts, setAttempts] = useState<AiSqlAttempt[]>([]);
  const [mistakes, setMistakes] = useState<SqlMistakeExample[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [goldOnly, setGoldOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<AiSqlAttemptPreview | null>(null);
  const [events, setEvents] = useState<AiSqlAttemptEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [reviewing, setReviewing] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(
    () => attempts.find((attempt) => attempt.id === selectedId) || attempts[0] || null,
    [attempts, selectedId]
  );
  const goldCount = useMemo(() => attempts.filter((attempt) => attempt.is_gold_example).length, [attempts]);

  useEffect(() => {
    setEmbedded(new URLSearchParams(window.location.search).get("embedded") === "1");
  }, []);

  useEffect(() => {
    loadAttempts(goldOnly);
  }, [goldOnly]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadAttempts(goldOnly, true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [goldOnly]);

  useEffect(() => {
    if (!selected?.id) {
      setPreview(null);
      setEvents([]);
      return;
    }
    loadPreview(selected.id);
    loadEvents(selected.id);
  }, [selected?.id]);

  useEffect(() => {
    if (!selected?.id) return;
    const timer = window.setInterval(() => {
      loadEvents(selected.id, true);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selected?.id]);

  async function loadAttempts(nextGoldOnly = goldOnly, silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      const data = await listAiSqlAttempts(nextGoldOnly);
      const mistakeData = await listSqlMistakeExamples();
      setAttempts(data);
      setMistakes(mistakeData);
      setSelectedId((current) => current && data.some((attempt) => attempt.id === current) ? current : data[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load attempts");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function review(attempt: AiSqlAttempt, status: "pending" | "correct" | "incorrect", approved: boolean) {
    setReviewing(attempt.id);
    setError("");
    try {
      const updated = await reviewAiSqlAttempt(attempt.id, status, approved);
      setAttempts((items) => items.map((item) => item.id === updated.id ? updated : item));
      setSelectedId(updated.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to review attempt");
    } finally {
      setReviewing("");
    }
  }

  async function loadPreview(attemptId: string) {
    setPreviewLoading(true);
    try {
      setPreview(await previewAiSqlAttempt(attemptId, 25));
    } catch (err) {
      setPreview({
        attempt_id: attemptId,
        columns: [],
        rows: [],
        row_count: 0,
        preview_limit: 25,
        execution_status: "failed",
        error: err instanceof Error ? err.message : "Unable to load preview"
      });
    } finally {
      setPreviewLoading(false);
    }
  }

  async function loadEvents(attemptId: string, silent = false) {
    if (!silent) setEventsLoading(true);
    try {
      setEvents(await listAiSqlAttemptEvents(attemptId));
    } catch {
      if (!silent) setEvents([]);
    } finally {
      if (!silent) setEventsLoading(false);
    }
  }

  return (
    <main className={embedded ? "admin-shell embedded-admin-shell" : "admin-shell"}>
      <header className="admin-header">
        <div>
          <h1>AI Safe Self-Learning Module Dashboard</h1>
          <p>Review generated SQL, approve correct runs, and promote safe examples into the gold dataset.</p>
        </div>
        <div className="admin-actions">
          <button className={goldOnly ? "active" : ""} onClick={() => setGoldOnly((value) => !value)} type="button">
            <ShieldCheck size={18} /> Gold only
          </button>
          <button onClick={() => loadAttempts()} type="button">
            <RefreshCw size={18} /> Refresh
          </button>
        </div>
      </header>

      {error && <div className="admin-error">{error}</div>}

      <section className="admin-kpis">
        <div><span>Total Attempts</span><strong>{attempts.length}</strong></div>
        <div><span>Successful</span><strong>{countByStatus(attempts, "success")}</strong></div>
        <div><span>Failed</span><strong>{countByStatus(attempts, "failed")}</strong></div>
        <div><span>Gold Examples</span><strong>{goldCount}</strong></div>
      </section>

      <section className="admin-workspace">
        <aside className="attempt-list">
          <div className="attempt-list-header">
            <span>Attempt Queue</span>
            <strong>{attempts.length}</strong>
          </div>
          {loading && <div className="attempt-empty">Loading attempts...</div>}
          {!loading && attempts.length === 0 && <div className="attempt-empty">No attempts found.</div>}
          {attempts.map((attempt) => (
            <button
              className={selected?.id === attempt.id ? "attempt-row active" : "attempt-row"}
              key={attempt.id}
              onClick={() => setSelectedId(attempt.id)}
              type="button"
            >
              <span>{shortId(attempt.id)}</span>
              <strong>{attempt.user_question}</strong>
              <small>{formatDate(attempt.created_at)}</small>
              <div className="attempt-row-meta">
                <em className={statusClass(attempt.execution_status)}>{attempt.execution_status || "pending"}</em>
                <em>{attempt.result_row_count ?? "-"} rows</em>
                {attempt.is_gold_example && <em className="gold">gold</em>}
              </div>
            </button>
          ))}
        </aside>

        <section className="attempt-detail">
          {!selected && <div className="attempt-empty">Select an attempt to review.</div>}
          {selected && (
            <>
              <div className="attempt-detail-header">
                <div>
                  <span>Attempt {shortId(selected.id)}</span>
                  <h2>{selected.user_question}</h2>
                </div>
                <div className="review-buttons">
                  <button
                    disabled={reviewing === selected.id}
                    onClick={() => review(selected, "correct", true)}
                    type="button"
                  >
                    <ShieldCheck size={18} /> Approve
                  </button>
                  <button
                    className="reject"
                    disabled={reviewing === selected.id}
                    onClick={() => review(selected, "pending", false)}
                    type="button"
                  >
                    <XCircle size={18} /> Reject
                  </button>
                  <button
                    disabled={reviewing === selected.id}
                    onClick={() => review(selected, "correct", false)}
                    type="button"
                  >
                    <CheckCircle2 size={18} /> Mark Correct
                  </button>
                  <button
                    className="reject"
                    disabled={reviewing === selected.id}
                    onClick={() => review(selected, "incorrect", false)}
                    type="button"
                  >
                    <XCircle size={18} /> Mark Incorrect
                  </button>
                </div>
              </div>

              <div className="attempt-metrics">
                <span className={statusClass(selected.validator_status)}>Validator: {selected.validator_status || "pending"}</span>
                <span className={statusClass(selected.execution_status)}>Execution: {selected.execution_status || "pending"}</span>
                <span><Database size={15} /> Rows: {selected.result_row_count ?? "-"}</span>
                <span>Provider: {selected.generation_provider || "-"}</span>
                <span>Model: {selected.generation_model || "-"}</span>
                <span>Generation: {formatMs(selected.generation_elapsed_ms)}</span>
                <span>Validator: {formatMs(selected.validator_elapsed_ms)}</span>
                <span>SQL: {formatMs(selected.execution_elapsed_ms)}</span>
                <span>Total: {formatMs(selected.total_elapsed_ms)}</span>
                <span>Feedback: {selected.user_feedback_status || "pending"}</span>
                <span>{selected.admin_approved ? "Admin approved" : "Not approved"}</span>
                <span>{selected.is_gold_example ? "Gold example" : "Not gold"}</span>
                <span>Created: {formatDate(selected.created_at)}</span>
                <span>Updated: {formatDate(selected.updated_at)}</span>
              </div>

              <section className="attempt-block">
                <h3>Review Summary</h3>
                <dl className="review-summary">
                  <div><dt>Final SQL</dt><dd>{compactSql(selected.final_sql)}</dd></div>
                  <div><dt>Validator Feedback</dt><dd>{selected.validator_feedback || "-"}</dd></div>
                  <div><dt>Execution Error</dt><dd>{selected.execution_error || "-"}</dd></div>
                </dl>
              </section>

              <section className="attempt-block live-run-block">
                <div className="result-preview-header">
                  <div>
                    <h3>Live Run Timeline</h3>
                    <p>Session events from generation, validation, retry, and execution. Auto-refreshes while this page is open.</p>
                  </div>
                  <button onClick={() => loadEvents(selected.id)} type="button">
                    <RefreshCw size={16} /> Refresh Logs
                  </button>
                </div>
                {eventsLoading && <div className="attempt-empty">Loading live events...</div>}
                {!eventsLoading && events.length === 0 && <div className="attempt-empty">No live events recorded for this attempt yet.</div>}
                {!eventsLoading && events.length > 0 && (
                  <ol className="run-event-list">
                    {events.map((event) => (
                      <li className={event.event_type === "detail" ? "detail" : ""} key={event.id}>
                        <div>
                          <span>{formatDate(event.created_at)}</span>
                          <strong>{event.step}</strong>
                        </div>
                        <p>{event.message}</p>
                        {event.payload_json && <pre>{event.payload_json}</pre>}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="attempt-block result-preview-block">
                <div className="result-preview-header">
                  <div>
                    <h3>SQL Result Preview</h3>
                    <p>Read-only preview from final SQL, limited to {preview?.preview_limit ?? 25} rows.</p>
                  </div>
                  <button onClick={() => loadPreview(selected.id)} type="button">
                    <RefreshCw size={16} /> Refresh Data
                  </button>
                </div>
                {previewLoading && <div className="attempt-empty">Loading table data...</div>}
                {!previewLoading && preview?.error && <div className="preview-error">{preview.error}</div>}
                {!previewLoading && preview && !preview.error && preview.rows.length === 0 && (
                  <div className="attempt-empty">Query executed, but no rows were returned.</div>
                )}
                {!previewLoading && preview && !preview.error && preview.rows.length > 0 && (
                  <div className="preview-table-wrap">
                    <table className="preview-table">
                      <thead>
                        <tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row, index) => (
                          <tr key={index}>
                            {preview.columns.map((column) => (
                              <td key={column}>{formatValue(row[column])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="attempt-block">
                <h3>Final SQL</h3>
                <pre>{selected.final_sql || "-"}</pre>
              </section>

              {selected.validator_feedback && (
                <section className="attempt-block">
                  <h3>Validator Feedback</h3>
                  <p>{selected.validator_feedback}</p>
                </section>
              )}

              {selected.execution_error && (
                <section className="attempt-block error">
                  <h3>Execution Error</h3>
                  <p>{selected.execution_error}</p>
                </section>
              )}

              <section className="attempt-block">
                <details>
                  <summary>Schema Snapshot</summary>
                  <pre>{selected.schema_snapshot || "-"}</pre>
                </details>
              </section>

              <section className="attempt-block">
                <h3>Generated SQL</h3>
                <pre>{selected.generated_sql || "-"}</pre>
              </section>

              {selected.regenerated_sql && (
                <section className="attempt-block">
                  <h3>Regenerated SQL</h3>
                  <pre>{selected.regenerated_sql}</pre>
                </section>
              )}

            </>
          )}
        </section>

        <aside className="mistake-panel">
          <div className="attempt-list-header">
            <span>Mistakes</span>
            <strong>{mistakes.length}</strong>
          </div>
          {mistakes.length === 0 && <div className="attempt-empty">No mistake examples yet.</div>}
          {mistakes.slice(0, 12).map((mistake) => (
            <article className="mistake-row" key={mistake.id}>
              <div>
                <strong>{mistake.mistake_type}</strong>
                <span>{mistake.risk_level}</span>
              </div>
              <p>{mistake.user_question}</p>
              <small>{mistake.validation_reason || mistake.validator_feedback || "-"}</small>
              <pre>{mistake.wrong_sql || "-"}</pre>
            </article>
          ))}
        </aside>
      </section>
    </main>
  );
}
