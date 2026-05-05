import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PnL, BS, ReportLine, api } from "../api/client";
import { Money } from "../components/Money";

const TODAY = new Date().toISOString().slice(0, 10);
const THIS_MONTH = TODAY.slice(0, 7);

type ReportTab = "pnl-bs" | "trial-balance" | "ap-aging" | "ar-aging" | "productivity" | "cash-flow";

export function Reports() {
  const [tab, setTab] = useState<ReportTab>("pnl-bs");
  const [period, setPeriod] = useState(THIS_MONTH);
  const [asOf, setAsOf] = useState(TODAY);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Reports</h2>

      <div className="flex flex-wrap gap-1">
        {[
          { id: "pnl-bs", label: "P&L / BS" },
          { id: "trial-balance", label: "Trial Balance" },
          { id: "ap-aging", label: "AP Aging" },
          { id: "ar-aging", label: "AR Aging" },
          { id: "productivity", label: "Productivity" },
          { id: "cash-flow", label: "Cash Flow" },
        ].map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id as ReportTab)}
            className={tab === id ? "btn" : "btn-ghost"}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "pnl-bs" && <PnlBsTab period={period} setPeriod={setPeriod} asOf={asOf} setAsOf={setAsOf} />}
      {tab === "trial-balance" && <TrialBalanceTab period={period} setPeriod={setPeriod} />}
      {tab === "ap-aging" && <ApAgingTab />}
      {tab === "ar-aging" && <ArAgingTab />}
      {tab === "productivity" && <ProductivityTab period={period} setPeriod={setPeriod} />}
      {tab === "cash-flow" && <CashFlowTab period={period} setPeriod={setPeriod} />}
    </div>
  );
}

// ---------- P&L / BS ----------

function PnlBsTab({
  period, setPeriod, asOf, setAsOf,
}: {
  period: string; setPeriod: (v: string) => void;
  asOf: string; setAsOf: (v: string) => void;
}) {
  const pnl = useQuery({ queryKey: ["pnl", period], queryFn: () => api.pnl(period) });
  const bs = useQuery({ queryKey: ["bs", asOf], queryFn: () => api.bs(asOf) });

  return (
    <>
      <section className="card">
        <div className="flex items-end gap-3 mb-4 flex-wrap">
          <div>
            <label className="block text-xs font-medium mb-1">Period</label>
            <input className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="2026-04" />
          </div>
          <DownloadBtn
            label="XLSX"
            onClick={() => api.downloadReport(`/reports/pnl/${period}?format=xlsx`, `pnl-${period}.xlsx`)}
          />
          <DownloadBtn
            label="PDF"
            onClick={() => api.downloadReport(`/reports/pnl/${period}?format=pdf`, `pnl-${period}.pdf`)}
          />
        </div>
        {pnl.isLoading ? <div className="text-sm text-ink-700">Loading P&amp;L…</div>
          : pnl.data ? <PnlTable pnl={pnl.data} />
          : <div className="text-sm text-red-600">P&amp;L unavailable</div>}
      </section>

      <section className="card">
        <div className="flex items-end gap-3 mb-4 flex-wrap">
          <div>
            <label className="block text-xs font-medium mb-1">As of</label>
            <input className="input w-44" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="2026-04-30" />
          </div>
          <DownloadBtn
            label="XLSX"
            onClick={() => api.downloadReport(`/reports/bs?as_of=${asOf}&format=xlsx`, `bs-${asOf}.xlsx`)}
          />
          <DownloadBtn
            label="PDF"
            onClick={() => api.downloadReport(`/reports/bs?as_of=${asOf}&format=pdf`, `bs-${asOf}.pdf`)}
          />
        </div>
        {bs.isLoading ? <div className="text-sm text-ink-700">Loading BS…</div>
          : bs.data ? <BsTable bs={bs.data} />
          : <div className="text-sm text-red-600">BS unavailable</div>}
      </section>
    </>
  );
}

// ---------- Trial Balance ----------

function TrialBalanceTab({ period, setPeriod }: { period: string; setPeriod: (v: string) => void }) {
  const tb = useQuery({ queryKey: ["trial-balance", period], queryFn: () => api.trialBalance(period) });
  return (
    <div className="card space-y-3">
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="block text-xs font-medium mb-1">Period (optional)</label>
          <input className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
        </div>
        <DownloadBtn
          label="XLSX"
          onClick={() =>
            api.downloadReport(
              `/reports/trial-balance?period=${period}&format=xlsx`,
              `trial-balance-${period}.xlsx`,
            )
          }
        />
      </div>
      {tb.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
      {tb.data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Code", "Name", "Dr", "Cr", "Net"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tb.data.lines.map((l) => (
                <tr key={l.account_code}>
                  <td className="table-cell font-mono">{l.account_code}</td>
                  <td className="table-cell">{l.account_name}</td>
                  <td className="table-cell font-mono text-right">{l.total_debit}</td>
                  <td className="table-cell font-mono text-right">{l.total_credit}</td>
                  <td className="table-cell font-mono text-right">{l.net_aed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- AP Aging ----------

function ApAgingTab() {
  const ap = useQuery({ queryKey: ["ap-aging"], queryFn: () => api.apAging() });
  return (
    <div className="card">
      {ap.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
      {ap.data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Tutor", "Currency", "0-30d", "31-60d", "61-90d", ">90d", "Total Owing"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ap.data.map((r) => (
                <tr key={r.tutor_id}>
                  <td className="table-cell">{r.name}</td>
                  <td className="table-cell">{r.payment_currency}</td>
                  <td className="table-cell font-mono text-right">{r.current_30}</td>
                  <td className="table-cell font-mono text-right">{r.days_31_60}</td>
                  <td className="table-cell font-mono text-right">{r.days_61_90}</td>
                  <td className="table-cell font-mono text-right text-red-700">{r.over_90}</td>
                  <td className="table-cell font-mono text-right font-semibold">{r.total_owing}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- AR Aging ----------

function ArAgingTab() {
  const ar = useQuery({ queryKey: ["ar-aging"], queryFn: () => api.arAging() });
  return (
    <div className="card">
      {ar.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
      {ar.data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Student", "0-30d", "31-90d", ">90d", "Total Balance AED"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ar.data.map((r) => (
                <tr key={r.student_id}>
                  <td className="table-cell">{r.name} ({r.display_id})</td>
                  <td className="table-cell font-mono text-right">{r.current_30}</td>
                  <td className="table-cell font-mono text-right">{r.days_31_90}</td>
                  <td className="table-cell font-mono text-right">{r.over_90}</td>
                  <td className="table-cell font-mono text-right font-semibold">{r.total_balance_aed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- Tutor Productivity ----------

function ProductivityTab({ period, setPeriod }: { period: string; setPeriod: (v: string) => void }) {
  const prod = useQuery({
    queryKey: ["tutor-productivity", period],
    queryFn: () => api.tutorProductivity(period),
  });
  return (
    <div className="card space-y-3">
      <div>
        <label className="block text-xs font-medium mb-1">Period (optional)</label>
        <input className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </div>
      {prod.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
      {prod.data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Tutor", "Sessions", "Penalties", "Penalty %", "Avg min", "No-shows"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {prod.data.map((r) => (
                <tr key={r.tutor_id}>
                  <td className="table-cell">{r.name} ({r.display_id})</td>
                  <td className="table-cell font-mono text-right">{r.total_sessions}</td>
                  <td className="table-cell font-mono text-right">{r.penalty_sessions}</td>
                  <td className={`table-cell font-mono text-right ${Number(r.penalty_pct) > 20 ? "text-red-600" : ""}`}>
                    {r.penalty_pct}%
                  </td>
                  <td className="table-cell font-mono text-right">{r.avg_conducted_min}</td>
                  <td className="table-cell font-mono text-right">{r.no_show_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- Cash Flow ----------

function CashFlowTab({ period, setPeriod }: { period: string; setPeriod: (v: string) => void }) {
  const cf = useQuery({ queryKey: ["cash-flow", period], queryFn: () => api.cashFlow(period) });
  return (
    <div className="card space-y-3">
      <div>
        <label className="block text-xs font-medium mb-1">Period</label>
        <input className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </div>
      {cf.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
      {cf.data && (
        <div className="space-y-4">
          <CfSection title="Operating Activities">
            <CfRow label="Net income" value={cf.data.operating.net_income} />
            <CfRow label="+ Depreciation" value={cf.data.operating.add_depreciation} />
            <CfRow label="+ Amortization" value={cf.data.operating.add_amortization} />
            <CfRow label="Δ Student wallets" value={cf.data.operating.change_in_student_wallets} />
            <CfRow label="Δ Tutor payables" value={cf.data.operating.change_in_tutor_payables} />
          </CfSection>
          <CfSection title="FX Effect">
            <CfRow label="FX effect on cash" value={cf.data.fx_effect_on_cash} />
          </CfSection>
          <CfSection title="Investing Activities">
            <CfRow label="Fixed asset additions" value={cf.data.investing.fixed_asset_additions} />
          </CfSection>
          <CfSection title="Financing Activities">
            <CfRow label="Equity injections" value={cf.data.financing.equity_injections} />
          </CfSection>
        </div>
      )}
    </div>
  );
}

function CfSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-700 mb-2">{title}</h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function CfRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

// ---------- Shared helpers ----------

function DownloadBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="btn-ghost text-xs" onClick={onClick}>
      ↓ {label}
    </button>
  );
}

function PnlTable({ pnl }: { pnl: PnL }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Block title="Revenue" lines={pnl.revenue} total={pnl.revenue_total} />
      <Block title="Cost of service" lines={pnl.cost_of_service} total={pnl.cost_total} />
      <Block title="Operating expenses" lines={pnl.operating_expenses} total={pnl.opex_total} />
      <Block title="Non-operating" lines={pnl.non_operating} total={pnl.non_op_total} />
      <div className="card lg:col-span-2 bg-ink-50">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <Cell label="Gross profit" v={pnl.gross_profit} />
          <Cell label="Operating profit" v={pnl.operating_profit} />
          <Cell label="Net profit" v={pnl.net_profit} />
          <Cell label="Revenue total" v={pnl.revenue_total} />
        </div>
      </div>
    </div>
  );
}

function BsTable({ bs }: { bs: BS }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Block title="Assets" lines={bs.assets} total={bs.assets_total} />
      <Block title="Liabilities" lines={bs.liabilities} total={bs.liabilities_total} />
      <Block title="Equity" lines={bs.equity} total={bs.equity_total} />
    </div>
  );
}

function Block({ title, lines, total }: { title: string; lines: ReportLine[]; total: string }) {
  return (
    <div>
      <h3 className="font-medium mb-2">{title}</h3>
      <table className="min-w-full">
        <thead>
          <tr>
            <th className="table-head">Code</th>
            <th className="table-head">Name</th>
            <th className="table-head text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.code}>
              <td className="table-cell font-mono text-xs">{l.code}</td>
              <td className="table-cell">{l.name}</td>
              <td className="table-cell"><Money amount={l.amount_aed} /></td>
            </tr>
          ))}
          <tr className="font-medium">
            <td className="table-cell" colSpan={2}>Total</td>
            <td className="table-cell"><Money amount={total} /></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Cell({ label, v }: { label: string; v: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-ink-700 mb-1">{label}</div>
      <div className="text-lg"><Money amount={v} /></div>
    </div>
  );
}
