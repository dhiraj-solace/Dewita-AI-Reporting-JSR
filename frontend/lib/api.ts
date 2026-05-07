export type ReportRequest = {
  question: string;
  start_date?: string | null;
  end_date?: string | null;
  limit: number;
  dry_run: boolean;
};

export type GeneratedReport = {
  attempt_id?: string | null;
  title: string;
  question: string;
  sql: string;
  explanation: string;
  assumptions: string[];
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  dry_run: boolean;
  warnings: string[];
  retry_attempts: RetryAttempt[];
};

export type RetryAttempt = {
  attempt: number;
  status: string;
  message: string;
  sql?: string | null;
  schema_issue?: string | null;
};

export type Health = {
  ok: boolean;
  database_configured: boolean;
  database_connected: boolean;
  ai_enabled: boolean;
};

export type AiSqlAttempt = {
  id: string;
  user_question: string;
  schema_snapshot?: string | null;
  generated_sql?: string | null;
  validator_status?: string | null;
  validator_feedback?: string | null;
  regenerated_sql?: string | null;
  final_sql?: string | null;
  execution_status?: string | null;
  execution_error?: string | null;
  result_row_count?: number | null;
  user_feedback_status?: string | null;
  admin_approved: boolean;
  is_gold_example: boolean;
  created_at: string;
  updated_at: string;
};

export type SqlMistakeExample = {
  id: string;
  query_attempt_id: string;
  user_question: string;
  wrong_sql?: string | null;
  validator_feedback?: string | null;
  validation_reason?: string | null;
  mistake_type: string;
  corrected_sql?: string | null;
  final_correct_sql?: string | null;
  risk_level: string;
  created_at: string;
};

export type AiSqlAttemptPreview = {
  attempt_id: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  preview_limit: number;
  execution_status: string;
  error?: string | null;
};

export class ApiError extends Error {
  title: string;
  solution?: string | null;
  statusCode?: number | null;
  retryAttempts: RetryAttempt[];

  constructor(
    message: string,
    retryAttempts: RetryAttempt[] = [],
    title = "Unable to run report",
    solution?: string | null,
    statusCode?: number | null
  ) {
    super(message);
    this.name = "ApiError";
    this.title = title;
    this.solution = solution;
    this.statusCode = statusCode;
    this.retryAttempts = retryAttempts;
  }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7000";

export async function runReport(payload: ReportRequest): Promise<GeneratedReport> {
  const response = await fetch(`${API_URL}/api/reports/query`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const payload = detail.detail;
    if (payload && typeof payload === "object") {
      throw new ApiError(
        payload.message || "Unable to run report",
        payload.retry_attempts || [],
        payload.title || "Unable to run report",
        payload.solution,
        payload.status_code
      );
    }
    throw new ApiError(payload || "Unable to run report");
  }

  return response.json();
}

export async function getHealth(): Promise<Health> {
  const response = await fetch(`${API_URL}/health`, {cache: "no-store"});
  if (!response.ok) {
    throw new Error("Backend health check failed");
  }
  return response.json();
}

export async function listAiSqlAttempts(goldOnly = false): Promise<AiSqlAttempt[]> {
  const params = new URLSearchParams({limit: "100", gold_only: String(goldOnly)});
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts?${params.toString()}`, {cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load AI SQL attempts");
  }
  return response.json();
}

export async function reviewAiSqlAttempt(
  attemptId: string,
  userFeedbackStatus: "pending" | "correct" | "incorrect",
  adminApproved: boolean
): Promise<AiSqlAttempt> {
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts/${attemptId}/review`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      user_feedback_status: userFeedbackStatus,
      admin_approved: adminApproved
    })
  });

  if (!response.ok) {
    throw new ApiError("Unable to review AI SQL attempt");
  }

  return response.json();
}

export async function listSqlMistakeExamples(): Promise<SqlMistakeExample[]> {
  const response = await fetch(`${API_URL}/api/admin/sql-mistake-examples?limit=100`, {cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load SQL mistake examples");
  }
  return response.json();
}

export async function previewAiSqlAttempt(attemptId: string, limit = 25): Promise<AiSqlAttemptPreview> {
  const params = new URLSearchParams({limit: String(limit)});
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts/${attemptId}/preview?${params.toString()}`, {cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load SQL result preview");
  }
  return response.json();
}
