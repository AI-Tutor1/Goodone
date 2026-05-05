import { ChangeEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function TutorPayouts() {
  const [file, setFile] = useState<File | null>(null);
  const [disbErr, setDisbErr] = useState<string | null>(null);
  const [filterPeriod, setFilterPeriod] = useState("");
  const [exportPeriod, setExportPeriod] = useState("");

  const disburse = useMutation({
    mutationFn: () => api.disbursePayroll(file!),
    onSuccess: () => { setDisbErr(null); history.refetch(); },
    onError: (e) => setDisbErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const history = useQuery({
    queryKey: ["disbursement-history", filterPeriod],
    queryFn: () => api.disbursementHistory(undefined, filterPeriod || undefined),
  });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Tutor Payouts</h2>

      {/* Disburse upload */}
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Upload Payout Sheet</h3>
        <p className="text-xs text-ink-700">
          Columns: tutor_id, amount_aed, payment_date, bank_ref (optional)
        </p>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setFile(e.target.files?.[0] ?? null);
            setDisbErr(null);
          }}
          className="input"
        />
        {disbErr && <div className="text-sm text-red-600">{disbErr}</div>}
        {disburse.data && (
          <div className="text-sm text-green-700">
            Disbursed {disburse.data.disbursed} payments · Total {disburse.data.total_aed} AED
            {disburse.data.errors.length > 0 && (
              <span className="text-yellow-700 ml-2">({disburse.data.errors.length} errors)</span>
            )}
          </div>
        )}
        <button
          className="btn"
          disabled={!file || disburse.isPending}
          onClick={() => { if (file) disburse.mutate(); }}
        >
          {disburse.isPending ? "Processing…" : "Disburse"}
        </button>
      </div>

      {/* Bank export */}
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Download Bank Export CSV</h3>
        <div className="flex gap-2 items-end">
          <div>
            <label className="block text-xs font-medium mb-1">Period (YYYY-MM)</label>
            <input
              className="input"
              placeholder="2026-05"
              value={exportPeriod}
              onChange={(e) => setExportPeriod(e.target.value)}
            />
          </div>
          <button
            className="btn"
            disabled={!exportPeriod}
            onClick={() => api.disbursementExport(exportPeriod)}
          >
            Download
          </button>
        </div>
      </div>

      {/* History */}
      <div className="card space-y-3">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold">Disbursement History</h3>
          <input
            className="input w-36 text-xs"
            placeholder="Filter period"
            value={filterPeriod}
            onChange={(e) => setFilterPeriod(e.target.value)}
          />
        </div>
        {history.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
        {history.data && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  {["#", "Tutor", "Amount AED", "Currency", "Bank Ref", "Date", "Period"].map((h) => (
                    <th key={h} className="table-head">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.data.disbursements.map((d) => (
                  <tr key={d.disbursement_id}>
                    <td className="table-cell font-mono">{d.disbursement_id}</td>
                    <td className="table-cell">{d.name} ({d.display_id})</td>
                    <td className="table-cell font-mono text-right">{d.amount_aed}</td>
                    <td className="table-cell">{d.payment_currency}</td>
                    <td className="table-cell font-mono text-xs">{d.bank_ref ?? "—"}</td>
                    <td className="table-cell">{d.payment_date}</td>
                    <td className="table-cell">{d.period}</td>
                  </tr>
                ))}
                {history.data.disbursements.length === 0 && (
                  <tr>
                    <td colSpan={7} className="table-cell text-center text-ink-700">No records</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
