import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function PeriodClose() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["periods"], queryFn: () => api.periods() });
  const [reason, setReason] = useState("");
  const [reopenTarget, setReopenTarget] = useState<string | null>(null);
  const [closeMsg, setCloseMsg] = useState<string | null>(null);
  const [reopenMsg, setReopenMsg] = useState<string | null>(null);

  const closeP = useMutation({
    mutationFn: (period: string) => api.closePeriod(period),
    onSuccess: () => {
      setCloseMsg("Period closed");
      qc.invalidateQueries({ queryKey: ["periods"] });
    },
    onError: (e: unknown) => {
      setCloseMsg(e instanceof ApiError ? JSON.stringify(e.body) : String(e));
    },
  });

  const reopenP = useMutation({
    mutationFn: ({ period, reason }: { period: string; reason: string }) =>
      api.reopenPeriod(period, reason),
    onSuccess: () => {
      setReopenMsg("Period reopened");
      setReopenTarget(null);
      setReason("");
      qc.invalidateQueries({ queryKey: ["periods"] });
    },
    onError: (e: unknown) => {
      setReopenMsg(e instanceof ApiError ? JSON.stringify(e.body) : String(e));
    },
  });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Period close</h2>
      {closeMsg && <div className="text-sm text-ink-700">{closeMsg}</div>}
      {reopenMsg && <div className="text-sm text-ink-700">{reopenMsg}</div>}
      <div className="card">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-head">Period</th>
              <th className="table-head">Status</th>
              <th className="table-head">Closed at</th>
              <th className="table-head">Closed by</th>
              <th className="table-head text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(list.data ?? []).map((p) => (
              <tr key={p.period}>
                <td className="table-cell font-mono">{p.period}</td>
                <td className="table-cell">{p.status}</td>
                <td className="table-cell">{p.closed_at ?? "—"}</td>
                <td className="table-cell">{p.closed_by ?? "—"}</td>
                <td className="table-cell text-right space-x-1">
                  {(p.status === "OPEN" || p.status === "IN_CLOSING" || p.status === "REOPENED") && (
                    <button onClick={() => closeP.mutate(p.period)} className="btn">
                      Close
                    </button>
                  )}
                  {p.status === "CLOSED" && (
                    <button onClick={() => setReopenTarget(p.period)} className="btn-ghost">
                      Reopen…
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {reopenTarget && (
        <div className="card">
          <h3 className="font-medium mb-2">Reopen {reopenTarget}</h3>
          <p className="text-sm text-ink-700 mb-2">
            CFO reopen requires a written reason of at least 30 characters.
          </p>
          <textarea
            className="input"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => reopenP.mutate({ period: reopenTarget, reason })}
              className="btn"
              disabled={reason.trim().length < 30}
            >
              Confirm reopen
            </button>
            <button onClick={() => setReopenTarget(null)} className="btn-ghost">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
