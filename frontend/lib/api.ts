export type ReportRequest = {
  question: string;
  start_date?: string | null;
  end_date?: string | null;
  limit: number;
  dry_run: boolean;
};

export type GeneratedReport = {
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

export class ApiError extends Error {
  retryAttempts: RetryAttempt[];

  constructor(message: string, retryAttempts: RetryAttempt[] = []) {
    super(message);
    this.name = "ApiError";
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
      throw new ApiError(payload.message || "Unable to run report", payload.retry_attempts || []);
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
