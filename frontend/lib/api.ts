export type ReportRequest = {
  question: string;
  report_category?: string | null;
  current_user_role?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  limit: number;
  dry_run: boolean;
  sql_generation_provider?: "openrouter" | "ollama" | "gemini" | "openai" | null;
};

export type UserPublic = {
  id: string;
  name: string;
  email: string;
  role_name: string;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type LoginResponse = {
  token: string;
  user: UserPublic;
};

export type UserCreatePayload = {
  name: string;
  email: string;
  password: string;
  role_name: string;
  is_active: boolean;
};

export type UserUpdatePayload = Partial<UserCreatePayload>;

export type ReportCategory = {
  id: string;
  label: string;
  enabled?: boolean;
};

export type GeneratedReport = {
  attempt_id?: string | null;
  saved_report_id?: string | null;
  generated_source?: string | null;
  report_category?: string | null;
  created_by_role?: string | null;
  created_by_user_id?: string | null;
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

export type SavedReportSummary = {
  id: string;
  title: string;
  question: string;
  report_category?: string | null;
  created_by_role?: string | null;
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  shared_by_name?: string | null;
  shared_label?: string | null;
  is_shared: boolean;
  is_new: boolean;
  can_export_shared: boolean;
  row_count: number;
  created_at: string;
};

export type SavedReportSharePayload = {
  recipient_email?: string | null;
  recipient_user_id?: string | null;
  message?: string | null;
  formats: Array<"pdf" | "xlsx">;
  can_export: boolean;
  current_user_role?: string | null;
};

export type SavedReportShareResponse = {
  status: string;
  message: string;
  delivery: Record<string, unknown>;
};

export type ReportAuditLog = {
  id: string;
  event_type: string;
  actor_role?: string | null;
  target_role?: string | null;
  report_id?: string | null;
  report_category?: string | null;
  action?: string | null;
  before_json?: string | null;
  after_json?: string | null;
  metadata_json?: string | null;
  created_at: string;
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

export type RoleReportPermission = {
  role_name: string;
  report_category: string;
  can_view: boolean;
  can_create: boolean;
  can_export: boolean;
  can_save: boolean;
  can_view_saved: boolean;
  data_scope: "all" | "role" | "team" | "project" | "self" | "none";
};

export type ReportPermissionsMatrix = {
  roles: string[];
  categories: ReportCategory[];
  permissions: RoleReportPermission[];
  scopes: RoleReportPermission["data_scope"][];
};

export type ScheduledReportPayload = {
  name: string;
  report_category: string;
  question: string;
  frequency: "daily" | "weekly" | "monthly";
  schedule_time: string;
  timezone: string;
  filters: Record<string, unknown>;
  recipients: Record<string, unknown>;
  current_user_role: string;
  sql_generation_provider?: "openrouter" | "ollama" | "gemini" | "openai" | null;
  limit: number;
  dry_run: boolean;
  export_formats: string[];
  execution_settings: Record<string, unknown>;
  is_active: boolean;
};

export type ScheduledReport = ScheduledReportPayload & {
  id: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  created_by_role?: string | null;
  created_at: string;
  updated_at: string;
};

export type ScheduledReportRun = {
  id: string;
  scheduled_report_id: string;
  saved_report_id?: string | null;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  generated_row_count?: number | null;
  metadata_json?: string | null;
};

export type AiSqlAttempt = {
  id: string;
  user_question: string;
  schema_snapshot?: string | null;
  generation_provider?: string | null;
  generation_model?: string | null;
  intent_validation_elapsed_ms?: number | null;
  generation_elapsed_ms?: number | null;
  validator_elapsed_ms?: number | null;
  execution_elapsed_ms?: number | null;
  total_elapsed_ms?: number | null;
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

export type AiSqlAttemptEvent = {
  id: string;
  attempt_id: string;
  step: string;
  message: string;
  event_type: string;
  payload_json?: string | null;
  created_at: string;
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
  use_in_context: boolean;
  validation_stage?: string;
  validator_source?: string;
  missing_table?: string | null;
  missing_column?: string | null;
  fix_hint?: string | null;
  mistake_fingerprint?: string | null;
  generated_output_number?: number | null;
  retry_number?: number | null;
  created_at: string;
};

export type SqlMistakeGroup = {
  group_key: string;
  user_question: string;
  mistake_type: string;
  reason: string;
  risk_level: string;
  occurrence_count: number;
  included_count: number;
  latest_created_at: string;
  examples: SqlMistakeExample[];
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

const API_URL = process.env.NEXT_PUBLIC_API_URL
  ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:7000");
const AUTH_TOKEN_KEY = "devita_auth_token";
const AUTH_USER_KEY = "devita_auth_user";

export function getStoredToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export function getStoredUser(): UserPublic | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserPublic;
  } catch {
    return null;
  }
}

export function storeAuthSession(session: LoginResponse) {
  if (typeof window === "undefined") return;
  localStorage.setItem(AUTH_TOKEN_KEY, session.token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(session.user));
}

export function clearAuthSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getStoredToken();
  return token ? {...extra, Authorization: `Bearer ${token}`} : extra;
}

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.json().catch(() => ({}));
  const detail = body.detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== "body").join(".") : "";
      return field ? `${field}: ${item.msg}` : item.msg;
    });
    return new ApiError(messages.join("; ") || fallback);
  }
  if (detail && typeof detail === "object") {
    return new ApiError(
      detail.message || fallback,
      detail.retry_attempts || [],
      detail.title || fallback,
      detail.solution,
      detail.status_code
    );
  }
  return new ApiError(detail || fallback);
}

export async function runReport(payload: ReportRequest): Promise<GeneratedReport> {
  const response = await fetch(`${API_URL}/api/reports/query`, {
    method: "POST",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw await apiError(response, "Unable to run report");
  }

  return response.json();
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({email, password})
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to login");
  }
  const session = await response.json();
  storeAuthSession(session);
  return session;
}

export async function getCurrentUser(): Promise<UserPublic> {
  const response = await fetch(`${API_URL}/api/auth/me`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    clearAuthSession();
    throw new ApiError("Login is required");
  }
  const user = await response.json();
  if (typeof window !== "undefined") localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  return user;
}

export async function listUsers(): Promise<UserPublic[]> {
  const response = await fetch(`${API_URL}/api/admin/users`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw await apiError(response, "Unable to load users");
  }
  return response.json();
}

export async function createUser(payload: UserCreatePayload): Promise<UserPublic> {
  const response = await fetch(`${API_URL}/api/admin/users`, {
    method: "POST",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to create user");
  }
  return response.json();
}

export async function updateUser(id: string, payload: UserUpdatePayload): Promise<UserPublic> {
  const response = await fetch(`${API_URL}/api/admin/users/${id}`, {
    method: "PATCH",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to update user");
  }
  return response.json();
}

export async function getHealth(): Promise<Health> {
  const response = await fetch(`${API_URL}/api/health`, {cache: "no-store"});
  if (!response.ok) {
    throw new Error("Backend health check failed");
  }
  return response.json();
}

export async function listReportCategories(): Promise<ReportCategory[]> {
  const response = await fetch(`${API_URL}/api/reports/categories`, {cache: "no-store"});
  if (!response.ok) {
    throw new Error("Unable to load report categories");
  }
  const payload = await response.json();
  return payload.categories || [];
}

export async function listReportPermissions(): Promise<ReportPermissionsMatrix> {
  const response = await fetch(`${API_URL}/api/admin/report-permissions`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load report permissions");
  }
  return response.json();
}

export async function updateReportPermissions(
  permissions: RoleReportPermission[],
  actorRole = "Super Admin"
): Promise<ReportPermissionsMatrix> {
  const params = new URLSearchParams({actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/report-permissions?${params.toString()}`, {
    method: "PUT",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({permissions})
  });
  if (!response.ok) {
    throw new ApiError("Unable to update report permissions");
  }
  return response.json();
}

export async function listReportAuditLogs(limit = 100): Promise<ReportAuditLog[]> {
  const params = new URLSearchParams({limit: String(limit)});
  const response = await fetch(`${API_URL}/api/admin/report-audit-logs?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load report audit logs");
  }
  return response.json();
}

export async function listScheduledReports(actorRole = "Super Admin"): Promise<ScheduledReport[]> {
  const params = new URLSearchParams({actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load scheduled reports");
  }
  return response.json();
}

export async function createScheduledReport(payload: ScheduledReportPayload, actorRole = "Super Admin"): Promise<ScheduledReport> {
  const params = new URLSearchParams({actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports?${params.toString()}`, {
    method: "POST",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to create scheduled report");
  }
  return response.json();
}

export async function updateScheduledReport(id: string, payload: ScheduledReportPayload, actorRole = "Super Admin"): Promise<ScheduledReport> {
  const params = new URLSearchParams({actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports/${id}?${params.toString()}`, {
    method: "PUT",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to update scheduled report");
  }
  return response.json();
}

export async function setScheduledReportStatus(id: string, isActive: boolean, actorRole = "Super Admin"): Promise<ScheduledReport> {
  const params = new URLSearchParams({is_active: String(isActive), actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports/${id}/status?${params.toString()}`, {
    method: "PATCH",
    headers: authHeaders()
  });
  if (!response.ok) {
    throw new ApiError("Unable to update scheduled report status");
  }
  return response.json();
}

export async function runScheduledReportNow(id: string, actorRole = "Super Admin"): Promise<ScheduledReportRun> {
  const params = new URLSearchParams({actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports/${id}/run-now?${params.toString()}`, {method: "POST", headers: authHeaders()});
  if (!response.ok) {
    throw new ApiError("Unable to run scheduled report");
  }
  return response.json();
}

export async function listScheduledReportRuns(id: string, actorRole = "Super Admin"): Promise<ScheduledReportRun[]> {
  const params = new URLSearchParams({limit: "50", actor_role: actorRole});
  const response = await fetch(`${API_URL}/api/admin/scheduled-reports/${id}/runs?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load scheduled report runs");
  }
  return response.json();
}

export async function listSavedReports(role = "Super Admin"): Promise<SavedReportSummary[]> {
  const params = new URLSearchParams({limit: "25", role});
  const response = await fetch(`${API_URL}/api/reports/saved?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load saved reports");
  }
  return response.json();
}

export async function getSavedReport(reportId: string, role = "Super Admin"): Promise<GeneratedReport> {
  const params = new URLSearchParams({role});
  const response = await fetch(`${API_URL}/api/reports/saved/${reportId}?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load saved report");
  }
  return response.json();
}

export function savedReportExportUrl(reportId: string, format: "pdf" | "xlsx", role = "Super Admin"): string {
  const params = new URLSearchParams({role});
  const token = getStoredToken();
  if (token) params.set("access_token", token);
  return `${API_URL}/api/reports/saved/${reportId}/export/${format}?${params.toString()}`;
}

export async function shareSavedReport(
  reportId: string,
  payload: SavedReportSharePayload
): Promise<SavedReportShareResponse> {
  const response = await fetch(`${API_URL}/api/reports/saved/${reportId}/share`, {
    method: "POST",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to share saved report");
  }
  return response.json();
}

export async function listAiSqlAttempts(goldOnly = false): Promise<AiSqlAttempt[]> {
  const params = new URLSearchParams({limit: "100", gold_only: String(goldOnly)});
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
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
    headers: authHeaders({"Content-Type": "application/json"}),
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

export async function listAiSqlAttemptEvents(attemptId: string): Promise<AiSqlAttemptEvent[]> {
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts/${attemptId}/events?limit=200`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load AI SQL attempt events");
  }
  return response.json();
}

export async function listSqlMistakeExamples(): Promise<SqlMistakeExample[]> {
  const response = await fetch(`${API_URL}/api/admin/sql-mistake-examples?limit=100`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load SQL mistake examples");
  }
  return response.json();
}

export async function listSqlMistakeGroups(): Promise<SqlMistakeGroup[]> {
  const response = await fetch(`${API_URL}/api/admin/sql-mistake-groups?limit=100`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load SQL mistake groups");
  }
  return response.json();
}

export async function setSqlMistakeContextUsage(
  mistakeId: string,
  useInContext: boolean
): Promise<SqlMistakeExample> {
  const response = await fetch(`${API_URL}/api/admin/sql-mistake-examples/${mistakeId}/context`, {
    method: "PATCH",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({use_in_context: useInContext})
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to update mistake context usage");
  }
  return response.json();
}

export async function setSqlMistakeGroupContextUsage(
  groupKey: string,
  useInContext: boolean
): Promise<SqlMistakeGroup> {
  const response = await fetch(`${API_URL}/api/admin/sql-mistake-groups/${groupKey}/context`, {
    method: "PATCH",
    headers: authHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({use_in_context: useInContext})
  });
  if (!response.ok) {
    throw await apiError(response, "Unable to update mistake group context usage");
  }
  return response.json();
}

export async function previewAiSqlAttempt(attemptId: string, limit = 25): Promise<AiSqlAttemptPreview> {
  const params = new URLSearchParams({limit: String(limit)});
  const response = await fetch(`${API_URL}/api/admin/ai-sql-attempts/${attemptId}/preview?${params.toString()}`, {headers: authHeaders(), cache: "no-store"});
  if (!response.ok) {
    throw new ApiError("Unable to load SQL result preview");
  }
  return response.json();
}
