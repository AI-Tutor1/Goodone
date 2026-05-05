import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const SEVERITY_BADGE: Record<string, string> = {
  error: "bg-red-100 text-red-700",
  warning: "bg-yellow-100 text-yellow-700",
  info: "bg-blue-100 text-blue-700",
};

export function DataQuality() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("OPEN");
  const [source, setSource] = useState("");
  const [resolveId, setResolveId] = useState<number | null>(null);
  const [resolution, setResolution] = useState("");

  const records = useQuery({
    queryKey: ["quarantine", status, source],
    queryFn: () => api.quarantine(status || "OPEN", source || undefined),
  });

  const resolve = useMutation({
    mutationFn: ({ id, res }: { id: number; res: string }) =>
      api.resolveQuarantine(id, res),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quarantine"] });
      setResolveId(null);
      setResolution("");
    },
  });

  const reprocess = useMutation({
    mutationFn: (id: number) => api.reprocessQuarantine(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quarantine"] }),
  });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Data Quality / Quarantine</h2>

      <div className="card flex flex-wrap gap-3">
        <div>
          <label className="block text-xs font-medium mb-1">Status</label>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="OPEN">Open</option>
            <option value="RESOLVED">Resolved</option>
            <option value="">All</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Source</label>
          <input
            className="input"
            placeholder="lms, sessions…"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
        </div>
      </div>

      {records.isLoading && <div className="text-sm text-ink-700">Loading…</div>}

      {records.data && (
        <div className="card space-y-3">
          <div className="text-xs text-ink-700">{records.data.records.length} record(s)</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  {["#", "Source", "Severity", "Status", "Error", "Created", "Actions"].map((h) => (
                    <th key={h} className="table-head">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.data.records.map((r) => (
                  <>
                    <tr key={r.quarantine_id}>
                      <td className="table-cell font-mono">{r.quarantine_id}</td>
                      <td className="table-cell">{r.source}</td>
                      <td className="table-cell">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_BADGE[r.severity] ?? "bg-ink-100 text-ink-700"}`}
                        >
                          {r.severity}
                        </span>
                      </td>
                      <td className="table-cell">{r.status}</td>
                      <td className="table-cell text-xs text-red-700 max-w-xs truncate">
                        {r.error_detail ?? "—"}
                      </td>
                      <td className="table-cell text-xs">{r.created_at.slice(0, 10)}</td>
                      <td className="table-cell space-x-1 whitespace-nowrap">
                        {r.status === "OPEN" && (
                          <>
                            <button
                              className="btn-ghost text-xs"
                              onClick={() => setResolveId(r.quarantine_id)}
                            >
                              Resolve
                            </button>
                            <button
                              className="btn-ghost text-xs"
                              disabled={reprocess.isPending}
                              onClick={() => reprocess.mutate(r.quarantine_id)}
                            >
                              Reprocess
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                    {resolveId === r.quarantine_id && (
                      <tr key={`resolve-${r.quarantine_id}`}>
                        <td colSpan={7} className="table-cell bg-ink-50">
                          <div className="flex gap-2 items-center">
                            <input
                              className="input flex-1 text-xs"
                              placeholder="Resolution note…"
                              value={resolution}
                              onChange={(e) => setResolution(e.target.value)}
                            />
                            <button
                              className="btn text-xs"
                              disabled={!resolution || resolve.isPending}
                              onClick={() =>
                                resolve.mutate({ id: r.quarantine_id, res: resolution })
                              }
                            >
                              Save
                            </button>
                            <button
                              className="btn-ghost text-xs"
                              onClick={() => setResolveId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {records.data.records.length === 0 && (
                  <tr>
                    <td colSpan={7} className="table-cell text-center text-ink-700">
                      No records
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
