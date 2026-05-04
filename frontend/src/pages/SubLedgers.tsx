import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Money } from "../components/Money";

const TABS = ["wallets", "tutors", "fixed-assets", "prepaids"] as const;
type Tab = (typeof TABS)[number];

export function SubLedgers() {
  const [tab, setTab] = useState<Tab>("wallets");

  const wallets = useQuery({ queryKey: ["wallets"], queryFn: () => api.wallets(), enabled: tab === "wallets" });
  const tutors = useQuery({ queryKey: ["tutors"], queryFn: () => api.tutorPayables(), enabled: tab === "tutors" });
  const assets = useQuery({ queryKey: ["assets"], queryFn: () => api.fixedAssets(), enabled: tab === "fixed-assets" });
  const prepaids = useQuery({ queryKey: ["prepaids"], queryFn: () => api.prepaids(), enabled: tab === "prepaids" });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Sub-ledgers</h2>
      <div className="flex gap-2 mb-2">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? "btn" : "btn-ghost"}
          >
            {t}
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
              {(wallets.data ?? []).map((r) => (
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
              {(tutors.data ?? []).map((r) => (
                <tr key={r.tutor_id}>
                  <td className="table-cell font-mono text-xs">{r.display_id}</td>
                  <td className="table-cell">{r.name}</td>
                  <td className="table-cell">{r.payment_currency}</td>
                  <td className="table-cell"><Money amount={r.balance_aed} /></td>
                  <td className="table-cell">
                    <Money amount={r.balance_original} currency={r.payment_currency} />
                  </td>
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
              {(assets.data ?? []).map((r) => (
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
              {(prepaids.data ?? []).map((r) => (
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
    </div>
  );
}
