import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, PreClosePreview, api } from "../api/client";

export function PeriodClose() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["periods"], queryFn: () => api.periods() });
  const [reason, setReason] = useState("");
  const [reopenTarget, setReopenTarget] = useState<string | null>(null);
  const [closeMsg, setCloseMsg] = useState<string | null>(null);
  const [reopenMsg, setReopenMsg] = useState<string | null>(null);
  const [previewTarget, setPreviewTarget] = useState<string | null>(null);
  const [previewPayload, setPreviewPayload] = useState({ posting_date: "", closing_rate_aed_per_pkr: "" });
  const [preview, setPreview] = useState<PreClosePreview | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  const closeP = useMutation({
    mutationFn: (period: string) => api.closePeriod(period),
    onSuccess: () => { setCloseMsg("Period closed"); qc.invalidateQueries({ queryKey: ["periods"] }); },
    onError: (e: unknown) => setCloseMsg(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
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
    onError: (e: unknown) => setReopenMsg(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const previewClose = useMutation({
    mutationFn: () => api.preClosePreview(previewTarget!, previewPayload),
    onSuccess: (r) => { setPreview(r); setPreviewErr(null); },
    onError: (e) => setPreviewErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
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
                <td className="table-cell text-right space-x-1 whitespace-nowrap">
                  {(p.status === "OPEN" || p.status === "REOPENED") && (
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => { setPreviewTarget(p.period); setPreview(null); setPreviewErr(null); }}
                    >
                      Preview Close…
                    </button>
                  )}
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

      {/* Pre-close dry-run panel */}
      {previewTarget && (
        <div className="card space-y-3">
          <h3 className="font-medium">Preview Close — {previewTarget} (dry run)</h3>
          <p className="text-xs text-ink-700">
            Runs all T+1 agents inside a database savepoint that is always rolled back.
            No GL changes are made.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1">Posting date</label>
              <input
                className="input"
                type="date"
                value={previewPayload.posting_date}
                onChange={(e) => setPreviewPayload((p) => ({ ...p, posting_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Closing rate AED/PKR</label>
              <input
                className="input font-mono"
                placeholder="87.50"
                value={previewPayload.closing_rate_aed_per_pkr}
                onChange={(e) =>
                  setPreviewPayload((p) => ({ ...p, closing_rate_aed_per_pkr: e.target.value }))
                }
              />
            </div>
          </div>
          {previewErr && <div className="text-sm text-red-600">{previewErr}</div>}
          <div className="flex gap-2">
            <button
              className="btn"
              disabled={
                !previewPayload.posting_date ||
                !previewPayload.closing_rate_aed_per_pkr ||
                previewClose.isPending
              }
              onClick={() => previewClose.mutate()}
            >
              {previewClose.isPending ? "Running preview…" : "Run Preview"}
            </button>
            <button className="btn-ghost" onClick={() => { setPreviewTarget(null); setPreview(null); }}>
              Cancel
            </button>
          </div>

          {preview && (
            <div className="bg-ink-50 rounded p-3 space-y-1 text-sm">
              <div className="font-semibold mb-2">Would post:</div>
              <PreviewRow label="FX revaluation JEs" count={preview.would_post.fx_jes} />
              <PreviewRow label="Depreciation JEs" count={preview.would_post.depreciation_jes} />
              <PreviewRow label="Prepaid amortization JEs" count={preview.would_post.prepaid_jes} />
              <PreviewRow label="Tuitional AI JE" count={preview.would_post.tuitional_ai_je ? 1 : 0} />
              <PreviewRow
                label="Intangible amortization JEs"
                count={preview.would_post.intangible_amortization_jes}
              />
            </div>
          )}
        </div>
      )}

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

function PreviewRow({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className={`font-mono font-semibold ${count > 0 ? "text-accent-600" : "text-ink-700"}`}>
        {count}
      </span>
    </div>
  );
}
