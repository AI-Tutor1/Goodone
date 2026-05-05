import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Money } from "../components/Money";

export function Profitability() {
  const [period, setPeriod] = useState<string>("");
  const profit = useQuery({
    queryKey: ["profitability", period],
    queryFn: () => api.profitability(period || undefined),
  });

  const rows = profit.data?.rows ?? [];
  const totalRevenue = rows.reduce((acc, r) => acc + Number(r.revenue_aed), 0);
  const totalMargin = rows.reduce((acc, r) => acc + Number(r.contribution_margin_aed), 0);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Per-enrollment profitability</h2>
      <div className="card">
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="block text-xs font-medium mb-1">Period (blank = lifetime)</label>
            <input
              className="input w-40"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="2026-04"
            />
          </div>
          <div className="ml-auto text-sm">
            <div className="text-ink-700">Sum revenue</div>
            <Money amount={totalRevenue.toFixed(2)} />
            <span className="mx-2 text-ink-200">·</span>
            <span className="text-ink-700">Contribution</span>{" "}
            <Money amount={totalMargin.toFixed(2)} />
          </div>
        </div>
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-head">Enrollment</th>
              <th className="table-head text-right">Revenue</th>
              <th className="table-head text-right">Direct cost</th>
              <th className="table-head text-right">Contribution</th>
              <th className="table-head text-right">Margin %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.enrollment_id}>
                <td className="table-cell font-mono text-xs">#{r.enrollment_id}</td>
                <td className="table-cell"><Money amount={r.revenue_aed} /></td>
                <td className="table-cell"><Money amount={r.direct_cost_aed} /></td>
                <td className="table-cell"><Money amount={r.contribution_margin_aed} /></td>
                <td className="table-cell money">{r.contribution_margin_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
