import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const STATUS_CLASS: Record<string, string> = {
  running: "text-blue-700",
  done: "text-green-700",
  failed: "text-red-700",
};

export function LmsSync() {
  const qc = useQueryClient();

  const syncs = useQuery({
    queryKey: ["lms-sync"],
    queryFn: () => api.lmsSyncStatus(20),
    refetchInterval: 15_000,
  });

  const syncNow = useMutation({
    mutationFn: () => api.lmsSyncNow(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lms-sync"] }),
  });

  const latest = syncs.data?.syncs?.[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">LMS Sync Status</h2>
        <button
          className="btn"
          onClick={() => syncNow.mutate()}
          disabled={syncNow.isPending || latest?.status === "running"}
        >
          {syncNow.isPending ? "Triggering…" : "Sync Now"}
        </button>
      </div>

      {latest && (
        <div className="card grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Status" value={latest.status} className={STATUS_CLASS[latest.status]} />
          <Stat label="Since" value={latest.since_date} />
          <Stat label="Fetched" value={String(latest.sessions_fetched ?? "—")} />
          <Stat label="Posted" value={String(latest.sessions_posted ?? "—")} />
          <Stat label="Skipped" value={String(latest.sessions_skipped ?? "—")} />
          <Stat label="Quarantined" value={String(latest.sessions_quarantined ?? "—")} />
          <Stat label="Started" value={latest.started_at.slice(0, 19).replace("T", " ")} />
          <Stat
            label="Completed"
            value={latest.completed_at ? latest.completed_at.slice(0, 19).replace("T", " ") : "—"}
          />
          {latest.error && (
            <div className="col-span-full text-xs text-red-700 font-mono bg-red-50 p-2 rounded">
              {latest.error}
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3 className="text-sm font-semibold mb-3">Sync History</h3>
        {syncs.isLoading && <div className="text-sm text-ink-700">Loading…</div>}
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["ID", "Status", "Since", "Fetched", "Posted", "Skipped", "Quarantined", "Started"].map(
                  (h) => <th key={h} className="table-head">{h}</th>,
                )}
              </tr>
            </thead>
            <tbody>
              {(syncs.data?.syncs ?? []).map((s) => (
                <tr key={s.sync_id}>
                  <td className="table-cell font-mono">{s.sync_id}</td>
                  <td className={`table-cell font-medium ${STATUS_CLASS[s.status] ?? ""}`}>{s.status}</td>
                  <td className="table-cell">{s.since_date}</td>
                  <td className="table-cell font-mono">{s.sessions_fetched ?? "—"}</td>
                  <td className="table-cell font-mono">{s.sessions_posted ?? "—"}</td>
                  <td className="table-cell font-mono">{s.sessions_skipped ?? "—"}</td>
                  <td className="table-cell font-mono">{s.sessions_quarantined ?? "—"}</td>
                  <td className="table-cell text-xs">{s.started_at.slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
              {(syncs.data?.syncs ?? []).length === 0 && (
                <tr>
                  <td colSpan={8} className="table-cell text-center text-ink-700">No syncs yet</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-xs text-ink-700">{label}</div>
      <div className={`font-mono font-semibold mt-0.5 ${className}`}>{value}</div>
    </div>
  );
}
