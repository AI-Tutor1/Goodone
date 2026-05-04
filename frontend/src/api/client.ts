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
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`api ${status}`);
  }
}

export const api = {
  health: () => request<{ status: string; coa: { version: number; accounts: number } }>("/"),

  login: (username: string, password: string) =>
    request<{ user_id: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: string }>("/auth/logout", { method: "POST" }),
  me: () => request<{ user_id: string; role: string }>("/auth/me"),

  pnl: (period: string) => request<PnL>(`/reports/pnl/${period}`),
  bs: (asOf: string) => request<BS>(`/reports/bs?as_of=${asOf}`),
  kpis: (period: string) => request<Kpis>(`/reports/kpis/${period}`),
  profitability: (period?: string) =>
    request<EnrollmentProfit[]>(
      period ? `/reports/profitability?period=${period}` : "/reports/profitability",
    ),

  wallets: () => request<WalletRow[]>("/subledgers/wallets"),
  tutorPayables: () => request<TutorRow[]>("/subledgers/tutor-payables"),
  fixedAssets: () => request<AssetRow[]>("/subledgers/fixed-assets"),
  prepaids: () => request<PrepaidRow[]>("/subledgers/prepaids"),

  postManualJe: (payload: ManualJePayload) =>
    request<PostedJournal>("/journal", { method: "POST", body: JSON.stringify(payload) }),

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

  periods: () => request<PeriodRow[]>("/periods"),
  closePeriod: (period: string) =>
    request<unknown>(`/periods/${period}/close`, { method: "POST" }),
  reopenPeriod: (period: string, reason: string) =>
    request<unknown>(`/periods/${period}/reopen`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  fxRates: (base = "AED", quote = "PKR", limit = 60) =>
    request<FxRow[]>(`/fx/rates?base=${base}&quote=${quote}&limit=${limit}`),
  fxOverride: (payload: { date: string; base: string; quote: string; rate: string }) =>
    request<{ ok: boolean }>("/fx/override", { method: "POST", body: JSON.stringify(payload) }),

  reconcile: () =>
    request<{ reconciliations: Record<string, ReconciliationResult> }>("/reconcile"),

  chatTools: () => request<ChatToolDescriptor[]>("/chat/tools"),
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
  attachment_url?: string | null;
  attachment_override_reason?: string | null;
  lines: ManualJeLine[];
}
export interface PostedJournal {
  je_id: number; date: string; period: string;
  total_aed: string; line_ids: number[];
}

export interface Sanction {
  id: number; department: string; title: string; amount_aed: string;
  status: string; created_at: string; created_by: string;
}

export interface PeriodRow {
  period: string; status: string;
  opened_at: string; closed_at: string | null; closed_by: string | null;
  reopened_at: string | null; reopened_by: string | null;
}

export interface FxRow {
  date: string; base: string; quote: string; rate: string; source: string;
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

export interface ChatTurnResponse {
  session_id: string;
  assistant: ChatMessagePayload;
  tool_calls: ChatMessagePayload[];
}
