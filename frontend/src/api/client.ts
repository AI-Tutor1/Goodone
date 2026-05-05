// Thin wrapper around fetch. All paths are proxied through Vite's /api prefix
// to the FastAPI backend on http://localhost:3002.

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = await resp.text();
    }
    throw new ApiError(resp.status, body);
  }
  if (resp.status === 204) return undefined as T;
  // 202 = TOTP required; return the JSON body without treating it as an error
  return (await resp.json()) as T;
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!resp.ok) {
    let body: unknown;
    try { body = await resp.json(); } catch { body = await resp.text(); }
    throw new ApiError(resp.status, body);
  }
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`api ${status}`);
  }
}

export const api = {
  health: () => request<{ status: string; coa: { version: number; accounts: number } }>("/"),

  // Auth
  login: (username: string, password: string) =>
    request<LoginResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  verifyTotp: (pending_token: string, otp_code: string) =>
    request<{ user_id: string; role: string }>("/auth/totp", {
      method: "POST",
      body: JSON.stringify({ pending_token, otp_code }),
    }),
  logout: () => request<{ ok: string }>("/auth/logout", { method: "POST" }),
  me: () => request<{ user_id: string; role: string }>("/auth/me"),
  totpSetup: () => request<{ provisioning_uri: string; secret: string }>("/auth/totp-setup"),

  // Reports
  pnl: (period: string, format?: "json" | "xlsx" | "pdf") =>
    request<PnL>(`/reports/pnl/${period}${format && format !== "json" ? `?format=${format}` : ""}`),
  bs: (asOf: string, format?: "json" | "xlsx" | "pdf") =>
    request<BS>(`/reports/bs?as_of=${asOf}${format && format !== "json" ? `&format=${format}` : ""}`),
  kpis: (period: string) => request<Kpis>(`/reports/kpis/${period}`),
  profitability: (period?: string, limit = 100, skip = 0) =>
    request<{ rows: EnrollmentProfit[]; limit: number; skip: number }>(
      `/reports/profitability?limit=${limit}&skip=${skip}${period ? `&period=${period}` : ""}`,
    ),
  trialBalance: (period?: string, format?: "json" | "xlsx" | "pdf") =>
    request<{ period: string | null; lines: TrialBalanceLine[] }>(
      `/reports/trial-balance${period ? `?period=${period}` : ""}${format && format !== "json" ? `${period ? "&" : "?"}format=${format}` : ""}`,
    ),
  apAging: () => request<ApAgingRow[]>("/reports/ap-aging"),
  arAging: () => request<ArAgingRow[]>("/reports/ar-aging"),
  tutorProductivity: (period?: string) =>
    request<TutorProductivityRow[]>(
      `/reports/tutor-productivity${period ? `?period=${period}` : ""}`,
    ),
  cashFlow: (period: string) => request<CashFlowReport>(`/reports/cash-flow/${period}`),
  budgetVsActual: (period: string) =>
    request<{ period: string; lines: BudgetVsActualLine[] }>(`/reports/budget-vs-actual/${period}`),

  // Download (returns a blob URL)
  downloadReport: async (path: string, filename: string) => {
    const resp = await fetch(`${BASE}${path}`, { credentials: "include" });
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  },

  // Sub-ledgers (paginated)
  wallets: (limit = 100, skip = 0) =>
    request<{ wallets: WalletRow[]; limit: number; skip: number }>(
      `/subledgers/wallets?limit=${limit}&skip=${skip}`,
    ),
  tutorPayables: (limit = 100, skip = 0) =>
    request<{ tutor_payables: TutorRow[]; limit: number; skip: number }>(
      `/subledgers/tutor-payables?limit=${limit}&skip=${skip}`,
    ),
  fixedAssets: (limit = 100, skip = 0) =>
    request<{ fixed_assets: AssetRow[]; limit: number; skip: number }>(
      `/subledgers/fixed-assets?limit=${limit}&skip=${skip}`,
    ),
  prepaids: (limit = 100, skip = 0) =>
    request<{ prepaids: PrepaidRow[]; limit: number; skip: number }>(
      `/subledgers/prepaids?limit=${limit}&skip=${skip}`,
    ),

  // File upload
  uploadFile: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<{ attachment_id: number; url: string }>("/uploads", fd);
  },

  // Manual JE
  postManualJe: (payload: ManualJePayload) =>
    request<PostedJournal>("/journal", { method: "POST", body: JSON.stringify(payload) }),
  reverseJe: (jeId: number, narration: string, onDate?: string) =>
    request<PostedJournal>(`/journal/${jeId}/reverse`, {
      method: "POST",
      body: JSON.stringify({ narration, on_date: onDate }),
    }),
  listJournalEntries: (limit = 50, skip = 0) =>
    request<{ entries: JournalEntry[] }>(`/journal?limit=${limit}&skip=${skip}`),

  // Sanctions
  sanctionsList: (status?: string) =>
    request<Sanction[]>(`/sanctions${status ? `?status=${status}` : ""}`),
  submitSanction: (payload: { department: string; title: string; amount_aed: string }) =>
    request<{ id: number; status: string }>("/sanctions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  faDecide: (id: number, approve: boolean) =>
    request<{ ok: boolean }>(`/sanctions/${id}/fa-decide`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),
  cfoDecide: (id: number, approve: boolean) =>
    request<{ ok: boolean; memo_je_id: number | null }>(`/sanctions/${id}/cfo-decide`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),

  // Periods
  periods: () => request<PeriodRow[]>("/periods"),
  preClosePreview: (period: string, payload: PreClosePayload) =>
    request<PreClosePreview>(`/periods/${period}/pre-close-preview`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  preClose: (period: string, payload: PreClosePayload) =>
    request<unknown>(`/periods/${period}/pre-close`, { method: "POST", body: JSON.stringify(payload) }),
  closePeriod: (period: string) =>
    request<unknown>(`/periods/${period}/close`, { method: "POST" }),
  reopenPeriod: (period: string, reason: string) =>
    request<unknown>(`/periods/${period}/reopen`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // FX
  fxRates: (base = "AED", quote = "PKR", limit = 60) =>
    request<FxRow[]>(`/fx/rates?base=${base}&quote=${quote}&limit=${limit}`),
  fxRateHistory: (base = "AED", quote = "PKR", from?: string, to?: string) =>
    request<FxRow[]>(
      `/fx/rates/history?base=${base}&quote=${quote}${from ? `&from=${from}` : ""}${to ? `&to=${to}` : ""}`,
    ),
  fxOverride: (payload: { date: string; base: string; quote: string; rate: string }) =>
    request<{ ok: boolean }>("/fx/override", { method: "POST", body: JSON.stringify(payload) }),

  // Ingestion
  uploadSessions: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<IngestionResult>("/ingestion/sessions", fd);
  },
  uploadSessionsSheets: (spreadsheet_id: string, tab_name: string) =>
    request<IngestionResult>("/ingestion/sessions/google-sheets", {
      method: "POST",
      body: JSON.stringify({ spreadsheet_id, tab_name }),
    }),
  uploadEnrollments: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<IngestionResult>("/ingestion/enrollments", fd);
  },
  uploadBankStatement: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<BankReconcileResult>("/ingestion/bank-statement", fd);
  },
  lmsSyncStatus: (limit = 10) =>
    request<{ syncs: LmsSyncRow[] }>(`/ingestion/lms/sync-status?limit=${limit}`),
  lmsSyncNow: () => request<LmsSyncRow>("/ingestion/lms/sync-now", { method: "POST" }),

  // Payroll
  disbursePayroll: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<DisburseResult>("/payroll/disburse", fd);
  },
  disbursementExport: (period: string) =>
    api.downloadReport(`/payroll/disbursement-export?period=${period}`, `payroll-export-${period}.csv`),
  disbursementHistory: (tutor_id?: number, period?: string, limit = 100, skip = 0) =>
    request<{ disbursements: DisbursementRow[]; limit: number; skip: number }>(
      `/payroll/disbursement-history?limit=${limit}&skip=${skip}${tutor_id !== undefined ? `&tutor_id=${tutor_id}` : ""}${period ? `&period=${period}` : ""}`,
    ),

  // Quarantine
  quarantine: (status = "OPEN", source?: string, limit = 100, skip = 0) =>
    request<{ records: QuarantineRow[]; limit: number; skip: number }>(
      `/quarantine?status=${status}&limit=${limit}&skip=${skip}${source ? `&source=${source}` : ""}`,
    ),
  resolveQuarantine: (id: number, resolution: string) =>
    request<{ quarantine_id: number; status: string }>(`/quarantine/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution }),
    }),
  reprocessQuarantine: (id: number) =>
    request<{ quarantine_id: number; result: string; error?: string }>(
      `/quarantine/${id}/reprocess`, { method: "POST" },
    ),

  // Budget
  upsertBudget: (period: string, account_code: string, amount_aed: string, notes?: string) =>
    request<{ period: string; account_code: string; amount_aed: string }>(
      `/budget/${period}/${account_code}`,
      { method: "POST", body: JSON.stringify({ amount_aed, notes }) },
    ),
  listBudget: (period: string) => request<BudgetEntry[]>(`/budget/${period}`),

  // Master data
  listStudents: (limit = 100, skip = 0) =>
    request<{ students: StudentRow[]; limit: number; skip: number }>(
      `/students?limit=${limit}&skip=${skip}`,
    ),
  createStudent: (display_id: string, name: string) =>
    request<{ student_id: number; display_id: string; name: string }>("/students", {
      method: "POST", body: JSON.stringify({ display_id, name }),
    }),
  listTutors: (limit = 100, skip = 0) =>
    request<{ tutors: TutorMasterRow[]; limit: number; skip: number }>(
      `/tutors?limit=${limit}&skip=${skip}`,
    ),
  createTutor: (display_id: string, name: string, payment_currency = "PKR") =>
    request<{ tutor_id: number; display_id: string; name: string }>("/tutors", {
      method: "POST", body: JSON.stringify({ display_id, name, payment_currency }),
    }),
  listEnrollments: (student_id?: number, tutor_id?: number, limit = 100, skip = 0) =>
    request<{ enrollments: EnrollmentRow[]; limit: number; skip: number }>(
      `/enrollments?limit=${limit}&skip=${skip}${student_id !== undefined ? `&student_id=${student_id}` : ""}${tutor_id !== undefined ? `&tutor_id=${tutor_id}` : ""}`,
    ),
  createEnrollment: (payload: EnrollmentCreate) =>
    request<{ enrollment_id: number; status: string }>("/enrollments", {
      method: "POST", body: JSON.stringify(payload),
    }),

  // System
  listBackups: () => request<{ backup_dir: string; backups: BackupFile[] }>("/system/backups"),
  triggerBackup: () => request<{ ok: boolean; stdout: string }>("/system/backups/trigger", { method: "POST" }),

  // Reconcile
  reconcile: () =>
    request<{ reconciliations: Record<string, ReconciliationResult> }>("/reconcile"),

  // Chat
  chatTools: () => request<ChatToolDescriptor[]>("/chat/tools"),
  chatSessions: () => request<{ sessions: ChatSessionListItem[] }>("/chat/sessions"),
  chatCreateSession: () =>
    request<{ id: string }>("/chat/sessions", { method: "POST" }),
  chatGetSession: (sid: string) => request<ChatSessionPayload>(`/chat/sessions/${sid}`),
  chatPost: (sid: string, message: string) =>
    request<ChatTurnResponse>(`/chat/sessions/${sid}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};

// ---- Types ----------------------------------------------------------------

export type LoginResult =
  | { user_id: string; role: string; requires_totp?: false }
  | { requires_totp: true; pending_token: string };

export interface ReportLine { code: string; name: string; amount_aed: string; }
export interface PnL {
  period: string;
  revenue: ReportLine[]; cost_of_service: ReportLine[];
  operating_expenses: ReportLine[]; non_operating: ReportLine[];
  revenue_total: string; cost_total: string; gross_profit: string;
  opex_total: string; operating_profit: string; non_op_total: string;
  net_profit: string;
}
export interface BS {
  as_of: string;
  assets: ReportLine[]; liabilities: ReportLine[]; equity: ReportLine[];
  assets_total: string; liabilities_total: string; equity_total: string;
}
export interface Kpis {
  period: string;
  revenue: string; cost_of_service: string; gross_profit: string;
  gross_margin_pct: string; operating_profit: string; net_profit: string;
  ebitda: string; no_show_revenue_share_pct: string;
}
export interface EnrollmentProfit {
  enrollment_id: number;
  revenue_aed: string; direct_cost_aed: string;
  contribution_margin_aed: string; contribution_margin_pct: string;
}
export interface TrialBalanceLine {
  account_code: string; account_name: string;
  total_debit: string; total_credit: string; net_aed: string;
}
export interface ApAgingRow {
  tutor_id: number; name: string; payment_currency: string;
  current_30: string; days_31_60: string; days_61_90: string;
  over_90: string; total_owing: string;
}
export interface ArAgingRow {
  student_id: number; display_id: string; name: string;
  current_30: string; days_31_90: string; over_90: string;
  total_balance_aed: string;
}
export interface TutorProductivityRow {
  tutor_id: number; display_id: string; name: string;
  total_sessions: number; penalty_sessions: number; penalty_pct: string;
  avg_conducted_min: string; no_show_count: number;
}
export interface CashFlowReport {
  period: string;
  operating: {
    net_income: string; add_depreciation: string; add_amortization: string;
    change_in_student_wallets: string; change_in_tutor_payables: string;
  };
  fx_effect_on_cash: string;
  investing: { fixed_asset_additions: string };
  financing: { equity_injections: string };
}
export interface BudgetVsActualLine {
  account_code: string; account_name: string;
  budget_aed: string; actual_aed: string; variance_aed: string;
}

export interface WalletRow {
  student_id: number; display_id: string; name: string;
  balance_aed: string; last_activity: string | null; dormant: boolean;
}
export interface TutorRow {
  tutor_id: number; display_id: string; name: string;
  payment_currency: "AED" | "PKR"; balance_aed: string; balance_original: string;
}
export interface AssetRow {
  asset_id: number; asset_class: string; description: string;
  cost_aed: string; accumulated_dep: string; nbv: string;
  useful_life_months: number; purchase_date: string; status: string;
}
export interface PrepaidRow {
  prepaid_id: number; account_code: string; description: string;
  total_aed: string; amortised: string; unamortised: string;
  total_months: number; start_date: string;
}

export interface ManualJeLine {
  account_code: string;
  debit_aed?: string;
  credit_aed?: string;
  sub_ledger_keys?: Record<string, string | number>;
  dimensions?: Record<string, string | number>;
}
export interface ManualJePayload {
  date: string;
  narration: string;
  attachment_id?: number | null;
  attachment_override_reason?: string | null;
  lines: ManualJeLine[];
}
export interface PostedJournal {
  je_id: number; date: string; period: string;
  total_aed: string; line_ids: number[];
}
export interface JournalEntry {
  je_id: number; date: string; period: string; narration: string;
  total_debit_aed: string; source: string; posted_by: string; posted_at: string;
}

export interface Sanction {
  id: number; department: string; title: string; amount_aed: string;
  status: string; created_at: string; created_by: string;
}

export interface PreClosePayload {
  posting_date: string;
  closing_rate_aed_per_pkr: string;
}
export interface PreClosePreview {
  period: string; dry_run: true;
  would_post: {
    fx_jes: number; depreciation_jes: number; prepaid_jes: number;
    tuitional_ai_je: boolean; intangible_amortization_jes: number;
  };
}

export interface PeriodRow {
  period: string; status: string;
  opened_at: string; closed_at: string | null; closed_by: string | null;
  reopened_at: string | null; reopened_by: string | null;
}

export interface FxRow {
  date: string; base: string; quote: string; rate: string; source: string;
}

export interface IngestionResult {
  accepted: number; skipped: number; quarantined: number;
  errors: Array<{ row: number; error: string }>;
}
export interface BankReconcileResult {
  matched: number; unmatched_bank: number; unmatched_gl: number; diff_aed: string;
}
export interface LmsSyncRow {
  sync_id: number; started_at: string; completed_at: string | null;
  since_date: string; sessions_fetched: number | null; sessions_posted: number | null;
  sessions_skipped: number | null; sessions_quarantined: number | null;
  status: string; error: string | null;
}

export interface DisburseResult {
  disbursed: number; total_aed: string;
  errors: Array<{ row: number; error: string }>;
}
export interface DisbursementRow {
  disbursement_id: number; tutor_id: number; name: string; display_id: string;
  amount_aed: string; payment_currency: string; bank_ref: string | null;
  payment_date: string; period: string; je_id: number; created_at: string;
}

export interface QuarantineRow {
  quarantine_id: number; source: string; source_ref: string | null;
  severity: string; status: string; raw_row: Record<string, unknown>;
  error_detail: string | null; resolution: string | null;
  created_at: string; resolved_at: string | null;
}

export interface BudgetEntry {
  budget_id: number; period: string; account_code: string; account_name: string;
  amount_aed: string; notes: string | null; created_by: string; created_at: string;
}

export interface StudentRow {
  student_id: number; display_id: string; name: string; active: boolean; created_at: string;
}
export interface TutorMasterRow {
  tutor_id: number; display_id: string; name: string;
  payment_currency: string; active: boolean; created_at: string;
}
export interface EnrollmentRow {
  enrollment_id: number; student_id: number; student_name: string;
  tutor_id: number; tutor_name: string; subject: string;
  rate_aed: string; start_date: string; end_date: string | null; status: string;
}
export interface EnrollmentCreate {
  student_id: number; tutor_id: number; subject: string;
  rate_aed: string; start_date: string; status?: string;
}

export interface BackupFile {
  filename: string; size_bytes: number; modified_at: number;
}

export interface ReconciliationResult {
  matches: boolean;
  gl_balance: string;
  sub_ledger_sum: string;
  diff: string;
  control_accounts: string[];
}

export interface ChatToolDescriptor {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ChatMessagePayload {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSessionPayload {
  id: string;
  created_at: string;
  messages: ChatMessagePayload[];
}

export interface ChatSessionListItem {
  session_id: string;
  message_count: number;
  created_at?: string;
  last_message_at?: string | null;
}

export interface ChatTurnResponse {
  session_id: string;
  assistant: ChatMessagePayload;
  tool_calls: ChatMessagePayload[];
}
