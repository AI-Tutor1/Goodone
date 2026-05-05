import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function FxRates() {
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [histFrom, setHistFrom] = useState("");
  const [histTo, setHistTo] = useState("");
  const [date, setDate] = useState("");
  const [rate, setRate] = useState("");

  const rates = useQuery({ queryKey: ["fx", "AED", "PKR"], queryFn: () => api.fxRates("AED", "PKR", 60) });
  const history = useQuery({
    queryKey: ["fx-history", "AED", "PKR", histFrom, histTo],
    queryFn: () => api.fxRateHistory("AED", "PKR", histFrom || undefined, histTo || undefined),
    enabled: showHistory,
  });

  const override = useMutation({
    mutationFn: () => api.fxOverride({ date, base: "AED", quote: "PKR", rate }),
    onSuccess: () => { setDate(""); setRate(""); qc.invalidateQueries({ queryKey: ["fx"] }); },
  });

  const onSubmit = (e: FormEvent) => { e.preventDefault(); override.mutate(); };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">FX rates AED → PKR</h2>

      <form onSubmit={onSubmit} className="card grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="input" placeholder="Date YYYY-MM-DD" value={date} onChange={(e) => setDate(e.target.value)} />
        <input className="input money" placeholder="Rate" value={rate} onChange={(e) => setRate(e.target.value)} />
        <button className="btn">Manual override</button>
      </form>

      <div className="card">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-head">Date</th>
              <th className="table-head">Rate</th>
              <th className="table-head">Source</th>
            </tr>
          </thead>
          <tbody>
            {(rates.data ?? []).map((r) => (
              <tr key={r.date + r.source}>
                <td className="table-cell font-mono">{r.date}</td>
                <td className="table-cell money">{r.rate}</td>
                <td className="table-cell">
                  {r.source === "manual" ? (
                    <span className="inline-flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-amber-500 inline-block" />
                      <span className="text-amber-700 font-medium">manual</span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-green-500 inline-block" />
                      <span className="text-green-700">{r.source}</span>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Historical chart / table */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Rate History</h3>
          <button className="btn-ghost text-xs" onClick={() => setShowHistory(!showHistory)}>
            {showHistory ? "Hide" : "Show"}
          </button>
        </div>
        {showHistory && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium mb-1">From</label>
                <input className="input" type="date" value={histFrom} onChange={(e) => setHistFrom(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">To</label>
                <input className="input" type="date" value={histTo} onChange={(e) => setHistTo(e.target.value)} />
              </div>
            </div>
            {history.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
            {history.data && history.data.length > 0 && (
              <>
                {/* Mini sparkline */}
                <svg viewBox={`0 0 ${history.data.length * 8} 50`} className="w-full h-16">
                  {(() => {
                    const rates = history.data.map((r) => Number(r.rate));
                    const min = Math.min(...rates);
                    const max = Math.max(...rates);
                    const range = max - min || 1;
                    const points = rates.map(
                      (v, i) => `${i * 8},${50 - ((v - min) / range) * 46}`,
                    ).join(" ");
                    return (
                      <polyline
                        points={points}
                        fill="none"
                        stroke="#3b82f6"
                        strokeWidth="1.5"
                      />
                    );
                  })()}
                </svg>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr>
                        {["Date", "Rate", "Source"].map((h) => (
                          <th key={h} className="table-head">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {history.data.map((r) => (
                        <tr key={r.date}>
                          <td className="table-cell font-mono">{r.date}</td>
                          <td className="table-cell font-mono">{r.rate}</td>
                          <td className="table-cell">
                            <span className={r.source === "manual" ? "text-amber-700" : "text-green-700"}>
                              {r.source}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {history.data?.length === 0 && (
              <div className="text-sm text-ink-700">No rates found for selected range</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
