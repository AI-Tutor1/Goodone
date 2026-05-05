import { ChangeEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, BankReconcileResult, api } from "../api/client";

export function BankReconciliation() {
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<BankReconcileResult | null>(null);

  const upload = useMutation({
    mutationFn: () => api.uploadBankStatement(file!),
    onSuccess: (r) => { setResult(r); setErr(null); },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Bank Reconciliation</h2>

      <div className="card space-y-3">
        <p className="text-xs text-ink-700">
          Upload a bank statement CSV. Columns auto-detected from standard bank export formats
          (Date, Amount, Description, Balance, Reference).
        </p>
        <input
          type="file"
          accept=".csv"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setFile(e.target.files?.[0] ?? null);
            setResult(null);
            setErr(null);
          }}
          className="input"
        />
        {err && <div className="text-sm text-red-600">{err}</div>}
        <button
          className="btn"
          disabled={!file || upload.isPending}
          onClick={() => { if (file) upload.mutate(); }}
        >
          {upload.isPending ? "Reconciling…" : "Upload & Reconcile"}
        </button>
      </div>

      {result && (
        <div className="card space-y-4">
          <h3 className="text-sm font-semibold">Reconciliation Result</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Matched" value={String(result.matched)} color="green" />
            <StatCard label="Unmatched (Bank)" value={String(result.unmatched_bank)} color="yellow" />
            <StatCard label="Unmatched (GL)" value={String(result.unmatched_gl)} color="yellow" />
            <StatCard
              label="Diff AED"
              value={result.diff_aed}
              color={result.diff_aed === "0" || result.diff_aed === "0.00" ? "green" : "red"}
            />
          </div>
          {(result.unmatched_bank === 0 && result.unmatched_gl === 0) && (
            <div className="text-sm text-green-700 font-medium">
              All transactions match — books are in agreement with the bank.
            </div>
          )}
          {(result.unmatched_bank > 0 || result.unmatched_gl > 0) && (
            <div className="text-sm text-yellow-700">
              Review unmatched items in the data quality quarantine.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: "green" | "yellow" | "red";
}) {
  const colors = {
    green: "bg-green-50 text-green-700",
    yellow: "bg-yellow-50 text-yellow-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <div className={`p-3 rounded text-center ${colors[color]}`}>
      <div className="text-2xl font-mono font-bold">{value}</div>
      <div className="text-xs mt-1">{label}</div>
    </div>
  );
}
