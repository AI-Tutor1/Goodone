import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function Settings() {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Settings</h2>
      <BackupPanel />
      <TotpPanel />
    </div>
  );
}

function BackupPanel() {
  const [log, setLog] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const backups = useQuery({ queryKey: ["backups"], queryFn: () => api.listBackups() });

  const trigger = useMutation({
    mutationFn: () => api.triggerBackup(),
    onSuccess: (r) => { setLog(r.stdout); setErr(null); backups.refetch(); },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Backup Status</h3>
        <button
          className="btn"
          disabled={trigger.isPending}
          onClick={() => trigger.mutate()}
        >
          {trigger.isPending ? "Running…" : "Run Backup Now"}
        </button>
      </div>

      {err && <div className="text-sm text-red-600">{err}</div>}
      {log && (
        <pre className="text-xs font-mono bg-ink-50 p-3 rounded overflow-auto max-h-40">{log}</pre>
      )}

      {backups.data && (
        <>
          <div className="text-xs text-ink-700">Backup dir: {backups.data.backup_dir}</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  {["File", "Size", "Modified"].map((h) => (
                    <th key={h} className="table-head">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {backups.data.backups.map((b) => (
                  <tr key={b.filename}>
                    <td className="table-cell font-mono text-xs">{b.filename}</td>
                    <td className="table-cell font-mono">
                      {(b.size_bytes / 1024 / 1024).toFixed(2)} MB
                    </td>
                    <td className="table-cell text-xs">
                      {new Date(b.modified_at * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
                {backups.data.backups.length === 0 && (
                  <tr>
                    <td colSpan={3} className="table-cell text-center text-ink-700">
                      No backups found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function TotpPanel() {
  const [show, setShow] = useState(false);

  const setup = useQuery({
    queryKey: ["totp-setup"],
    queryFn: () => api.totpSetup(),
    enabled: show,
    retry: false,
  });

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">TOTP Setup</h3>
        <button className="btn-ghost" onClick={() => setShow(!show)}>
          {show ? "Hide" : "Show Setup"}
        </button>
      </div>

      {show && (
        <>
          {setup.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
          {setup.isError && (
            <div className="text-sm text-red-600">
              {setup.error instanceof ApiError
                ? "TOTP not configured on this server (CFO_TOTP_SECRET not set)"
                : String(setup.error)}
            </div>
          )}
          {setup.data && (
            <div className="space-y-2">
              <p className="text-xs text-ink-700">
                Scan this URI with your authenticator app (Google Authenticator, Authy, etc.).
              </p>
              <div className="font-mono text-xs bg-ink-50 p-2 rounded break-all">
                {setup.data.provisioning_uri}
              </div>
              <div>
                <span className="text-xs font-medium">Secret: </span>
                <span className="font-mono text-xs">{setup.data.secret}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
