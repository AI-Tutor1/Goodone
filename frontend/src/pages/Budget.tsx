import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function Budget() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [accountCode, setAccountCode] = useState("");
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const entries = useQuery({
    queryKey: ["budget", period],
    queryFn: () => api.listBudget(period),
    enabled: !!period,
  });

  const variance = useQuery({
    queryKey: ["budget-vs-actual", period],
    queryFn: () => api.budgetVsActual(period),
    enabled: !!period,
  });

  const upsert = useMutation({
    mutationFn: () => api.upsertBudget(period, accountCode, amount, notes || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["budget", period] });
      qc.invalidateQueries({ queryKey: ["budget-vs-actual", period] });
      setAccountCode(""); setAmount(""); setNotes(""); setErr(null);
    },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Budget</h2>

      <div className="card space-y-3">
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Period</label>
            <input
              className="input"
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Set / Update Budget Entry</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Account Code</label>
            <input
              className="input font-mono"
              placeholder="5010"
              value={accountCode}
              onChange={(e) => setAccountCode(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Amount AED</label>
            <input
              className="input font-mono"
              placeholder="10000.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Notes (optional)</label>
            <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        {err && <div className="text-sm text-red-600">{err}</div>}
        <button
          className="btn"
          disabled={!period || !accountCode || !amount || upsert.isPending}
          onClick={() => upsert.mutate()}
        >
          Save Budget Entry
        </button>
      </div>

      {variance.data && (
        <div className="card">
          <h3 className="text-sm font-semibold mb-3">Budget vs Actual — {period}</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  {["Account", "Name", "Budget AED", "Actual AED", "Variance AED"].map((h) => (
                    <th key={h} className="table-head">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {variance.data.lines.map((l) => {
                  const v = Number(l.variance_aed);
                  return (
                    <tr key={l.account_code}>
                      <td className="table-cell font-mono">{l.account_code}</td>
                      <td className="table-cell">{l.account_name ?? "—"}</td>
                      <td className="table-cell font-mono text-right">{l.budget_aed}</td>
                      <td className="table-cell font-mono text-right">{l.actual_aed}</td>
                      <td
                        className={`table-cell font-mono text-right font-medium ${v > 0 ? "text-red-600" : v < 0 ? "text-green-600" : ""}`}
                      >
                        {l.variance_aed}
                      </td>
                    </tr>
                  );
                })}
                {variance.data.lines.length === 0 && (
                  <tr>
                    <td colSpan={5} className="table-cell text-center text-ink-700">
                      No budget entries for this period
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
