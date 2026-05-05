import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Money } from "../components/Money";

const TABS = ["wallets", "tutors", "fixed-assets", "prepaids", "ap-aging", "ar-aging"] as const;
type Tab = (typeof TABS)[number];

const PAGE = 100;

export function SubLedgers() {
  const [tab, setTab] = useState<Tab>("wallets");
  const [skip, setSkip] = useState(0);

  const resetPage = (t: Tab) => { setTab(t); setSkip(0); };

  const wallets = useQuery({
    queryKey: ["wallets", skip],
    queryFn: () => api.wallets(PAGE, skip),
    enabled: tab === "wallets",
  });
  const tutors = useQuery({
    queryKey: ["tutor-payables", skip],
    queryFn: () => api.tutorPayables(PAGE, skip),
    enabled: tab === "tutors",
  });
  const assets = useQuery({
    queryKey: ["assets", skip],
    queryFn: () => api.fixedAssets(PAGE, skip),
    enabled: tab === "fixed-assets",
  });
  const prepaids = useQuery({
    queryKey: ["prepaids", skip],
    queryFn: () => api.prepaids(PAGE, skip),
    enabled: tab === "prepaids",
  });
  const apAging = useQuery({
    queryKey: ["ap-aging"],
    queryFn: () => api.apAging(),
    enabled: tab === "ap-aging",
  });
  const arAging = useQuery({
    queryKey: ["ar-aging"],
    queryFn: () => api.arAging(),
    enabled: tab === "ar-aging",
  });

  const paginatedCount = (() => {
    if (tab === "wallets") return wallets.data?.wallets.length;
    if (tab === "tutors") return tutors.data?.tutor_payables.length;
    if (tab === "fixed-assets") return assets.data?.fixed_assets.length;
    if (tab === "prepaids") return prepaids.data?.prepaids.length;
    return undefined;
  })();

  const paginated = paginatedCount !== undefined;

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Sub-ledgers</h2>
      <div className="flex flex-wrap gap-1 mb-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => resetPage(t)} className={tab === t ? "btn" : "btn-ghost"}>
            {t === "ap-aging" ? "AP Aging" : t === "ar-aging" ? "AR Aging" : t}
          </button>
        ))}
      </div>

      {tab === "wallets" && (
        <div className="card">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-head">Student</th>
                <th className="table-head">Name</th>
                <th className="table-head text-right">Balance</th>
                <th className="table-head">Last activity</th>
                <th className="table-head">Status</th>
              </tr>
            </thead>
            <tbody>
              {(wallets.data?.wallets ?? []).map((r) => (
                <tr key={r.student_id}>
                  <td className="table-cell font-mono text-xs">{r.display_id}</td>
                  <td className="table-cell">{r.name}</td>
                  <td className="table-cell"><Money amount={r.balance_aed} /></td>
                  <td className="table-cell">{r.last_activity ?? "—"}</td>
                  <td className="table-cell">
                    {r.dormant ? <span className="text-amber-700">dormant &gt;12mo</span> : "active"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "tutors" && (
        <div className="card">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-head">Tutor</th>
                <th className="table-head">Name</th>
                <th className="table-head">Currency</th>
                <th className="table-head text-right">Balance (AED)</th>
                <th className="table-head text-right">Balance (orig)</th>
              </tr>
            </thead>
            <tbody>
              {(tutors.data?.tutor_payables ?? []).map((r) => (
                <tr key={r.tutor_id}>
                  <td className="table-cell font-mono text-xs">{r.display_id}</td>
                  <td className="table-cell">{r.name}</td>
                  <td className="table-cell">{r.payment_currency}</td>
                  <td className="table-cell"><Money amount={r.balance_aed} /></td>
                  <td className="table-cell"><Money amount={r.balance_original} currency={r.payment_currency} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "fixed-assets" && (
        <div className="card">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-head">Asset</th>
                <th className="table-head">Class</th>
                <th className="table-head">Description</th>
                <th className="table-head text-right">Cost</th>
                <th className="table-head text-right">Accum dep</th>
                <th className="table-head text-right">NBV</th>
              </tr>
            </thead>
            <tbody>
              {(assets.data?.fixed_assets ?? []).map((r) => (
                <tr key={r.asset_id}>
                  <td className="table-cell font-mono text-xs">#{r.asset_id}</td>
                  <td className="table-cell">{r.asset_class}</td>
                  <td className="table-cell">{r.description}</td>
                  <td className="table-cell"><Money amount={r.cost_aed} /></td>
                  <td className="table-cell"><Money amount={r.accumulated_dep} /></td>
                  <td className="table-cell"><Money amount={r.nbv} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "prepaids" && (
        <div className="card">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-head">Prepaid</th>
                <th className="table-head">Account</th>
                <th className="table-head">Description</th>
                <th className="table-head text-right">Total</th>
                <th className="table-head text-right">Amortised</th>
                <th className="table-head text-right">Unamortised</th>
              </tr>
            </thead>
            <tbody>
              {(prepaids.data?.prepaids ?? []).map((r) => (
                <tr key={r.prepaid_id}>
                  <td className="table-cell font-mono text-xs">#{r.prepaid_id}</td>
                  <td className="table-cell">{r.account_code}</td>
                  <td className="table-cell">{r.description}</td>
                  <td className="table-cell"><Money amount={r.total_aed} /></td>
                  <td className="table-cell"><Money amount={r.amortised} /></td>
                  <td className="table-cell"><Money amount={r.unamortised} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "ap-aging" && (
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Tutor", "Currency", "0-30d", "31-60d", "61-90d", ">90d", "Total Owing"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(apAging.data ?? []).map((r) => (
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

      {tab === "ar-aging" && (
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["Student", "0-30d", "31-90d", ">90d", "Total Balance AED"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(arAging.data ?? []).map((r) => (
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

      {paginated && (
        <div className="flex items-center gap-3 text-sm">
          <button className="btn-ghost" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE))}>
            Prev
          </button>
          <span className="text-ink-700">Showing {skip + 1}–{skip + (paginatedCount ?? 0)}</span>
          <button
            className="btn-ghost"
            disabled={(paginatedCount ?? 0) < PAGE}
            onClick={() => setSkip(skip + PAGE)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
