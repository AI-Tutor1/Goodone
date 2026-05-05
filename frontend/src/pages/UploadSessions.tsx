import { ChangeEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, IngestionResult, api } from "../api/client";

type Mode = "csv" | "sheets";

export function UploadSessions() {
  const [mode, setMode] = useState<Mode>("csv");
  const [file, setFile] = useState<File | null>(null);
  const [sheetsId, setSheetsId] = useState("");
  const [sheetsTab, setSheetsTab] = useState("sessions");
  const [result, setResult] = useState<IngestionResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const uploadCsv = useMutation({
    mutationFn: () => api.uploadSessions(file!),
    onSuccess: (r) => { setResult(r); setErr(null); },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const uploadSheets = useMutation({
    mutationFn: () => api.uploadSessionsSheets(sheetsId, sheetsTab),
    onSuccess: (r) => { setResult(r); setErr(null); },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const isPending = uploadCsv.isPending || uploadSheets.isPending;

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    setResult(null);
    setErr(null);
  };

  const onSubmit = () => {
    setErr(null);
    setResult(null);
    if (mode === "csv") {
      if (!file) { setErr("Select a file first"); return; }
      uploadCsv.mutate();
    } else {
      if (!sheetsId) { setErr("Enter a Spreadsheet ID"); return; }
      uploadSheets.mutate();
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Upload Sessions</h2>

      <div className="card space-y-4">
        <div className="flex gap-2">
          {(["csv", "sheets"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={mode === m ? "btn" : "btn-ghost"}
            >
              {m === "csv" ? "CSV / XLSX" : "Google Sheets"}
            </button>
          ))}
        </div>

        {mode === "csv" ? (
          <div>
            <label className="block text-xs font-medium mb-1">
              File (CSV or XLSX — columns: session_id, enrollment_id, scheduled_minutes,
              conducted_minutes, status, occurred_on)
            </label>
            <input type="file" accept=".csv,.xlsx,.xls" onChange={onFileChange} className="input" />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1">Spreadsheet ID</label>
              <input className="input" value={sheetsId} onChange={(e) => setSheetsId(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Tab name</label>
              <input className="input" value={sheetsTab} onChange={(e) => setSheetsTab(e.target.value)} />
            </div>
          </div>
        )}

        {err && <div className="text-sm text-red-600">{err}</div>}

        <button className="btn" onClick={onSubmit} disabled={isPending}>
          {isPending ? "Uploading…" : "Upload"}
        </button>
      </div>

      {result && (
        <div className="card space-y-3">
          <h3 className="font-semibold text-sm">Result</h3>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="p-3 bg-green-50 rounded">
              <div className="text-2xl font-mono font-bold text-green-700">{result.accepted}</div>
              <div className="text-xs text-green-600 mt-1">Accepted</div>
            </div>
            <div className="p-3 bg-ink-50 rounded">
              <div className="text-2xl font-mono font-bold text-ink-700">{result.skipped}</div>
              <div className="text-xs text-ink-600 mt-1">Skipped (duplicate)</div>
            </div>
            <div className="p-3 bg-yellow-50 rounded">
              <div className="text-2xl font-mono font-bold text-yellow-700">{result.quarantined}</div>
              <div className="text-xs text-yellow-600 mt-1">Quarantined</div>
            </div>
          </div>

          {result.errors.length > 0 && (
            <details>
              <summary className="text-sm cursor-pointer text-red-600">
                {result.errors.length} row error(s)
              </summary>
              <ul className="mt-2 space-y-1">
                {result.errors.map((e, i) => (
                  <li key={i} className="text-xs font-mono text-red-700">
                    Row {e.row}: {e.error}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
