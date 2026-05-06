"use client";

import {useEffect, useMemo, useState} from "react";
import {CheckCircle2, Database, RefreshCw, ShieldCheck, XCircle} from "lucide-react";
import {AiSqlAttempt, listAiSqlAttempts, reviewAiSqlAttempt} from "@/lib/api";

function shortId(id: string) {
  return id.slice(0, 8);
}

function statusClass(value?: string | null) {
  if (!value) return "muted";
  return value.toLowerCase() === "success" ? "success" : value.toLowerCase() === "failed" ? "failed" : "muted";
}

export default function AiSqlAttemptsAdminPage() {
  const [attempts, setAttempts] = useState<AiSqlAttempt[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [goldOnly, setGoldOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(
    () => attempts.find((attempt) => attempt.id === selectedId) || attempts[0] || null,
    [attempts, selectedId]
  );

  useEffect(() => {
    loadAttempts(goldOnly);
  }, [goldOnly]);

  async function loadAttempts(nextGoldOnly = goldOnly) {
    setLoading(true);
    setError("");
    try {
      const data = await listAiSqlAttempts(nextGoldOnly);
      setAttempts(data);
      setSelectedId((current) => current && data.some((attempt) => attempt.id === current) ? current : data[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load attempts");
    } finally {
      setLoading(false);
    }
  }

  async function review(attempt: AiSqlAttempt, status: "correct" | "incorrect", approved: boolean) {
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

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <h1>AI SQL Attempts</h1>
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

      <section className="admin-grid">
        <aside className="attempt-list">
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
              <small>
                {attempt.execution_status || "pending"}
                {attempt.is_gold_example ? " | gold" : ""}
              </small>
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
                    <CheckCircle2 size={18} /> Correct + Approve
                  </button>
                  <button
                    className="reject"
                    disabled={reviewing === selected.id}
                    onClick={() => review(selected, "incorrect", false)}
                    type="button"
                  >
                    <XCircle size={18} /> Incorrect
                  </button>
                </div>
              </div>

              <div className="attempt-metrics">
                <span className={statusClass(selected.validator_status)}>Validator: {selected.validator_status || "pending"}</span>
                <span className={statusClass(selected.execution_status)}>Execution: {selected.execution_status || "pending"}</span>
                <span><Database size={15} /> Rows: {selected.result_row_count ?? "-"}</span>
                <span>{selected.admin_approved ? "Admin approved" : "Not approved"}</span>
                <span>{selected.is_gold_example ? "Gold example" : "Not gold"}</span>
              </div>

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
                <h3>Generated SQL</h3>
                <pre>{selected.generated_sql || "-"}</pre>
              </section>

              {selected.regenerated_sql && (
                <section className="attempt-block">
                  <h3>Regenerated SQL</h3>
                  <pre>{selected.regenerated_sql}</pre>
                </section>
              )}

              <section className="attempt-block">
                <h3>Final SQL</h3>
                <pre>{selected.final_sql || "-"}</pre>
              </section>
            </>
          )}
        </section>
      </section>
    </main>
  );
}
