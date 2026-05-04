import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Money } from "../components/Money";

const CURRENT_PERIOD = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
})();

export function Home() {
  const kpis = useQuery({ queryKey: ["kpis", CURRENT_PERIOD], queryFn: () => api.kpis(CURRENT_PERIOD) });
  const recon = useQuery({ queryKey: ["reconcile"], queryFn: () => api.reconcile() });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Current month: {CURRENT_PERIOD}</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Revenue" value={kpis.data?.revenue} loading={kpis.isLoading} />
        <KpiCard label="Gross profit" value={kpis.data?.gross_profit} loading={kpis.isLoading} />
        <KpiCard label="Operating profit" value={kpis.data?.operating_profit} loading={kpis.isLoading} />
        <KpiCard label="EBITDA" value={kpis.data?.ebitda} loading={kpis.isLoading} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <PctCard label="Gross margin" pct={kpis.data?.gross_margin_pct} loading={kpis.isLoading} />
        <PctCard
          label="No-show revenue share"
          pct={kpis.data?.no_show_revenue_share_pct}
          loading={kpis.isLoading}
        />
        <KpiCard label="Net profit" value={kpis.data?.net_profit} loading={kpis.isLoading} />
      </div>

      <section className="card">
        <h3 className="font-medium mb-3">Sub-ledger reconciliation</h3>
        {recon.isLoading && <div className="text-sm text-ink-700">Checking…</div>}
        {recon.data && (
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-head">Sub-ledger</th>
                <th className="table-head">GL balance</th>
                <th className="table-head">Sub-ledger sum</th>
                <th className="table-head">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(recon.data.reconciliations).map(([name, r]) => (
                <tr key={name}>
                  <td className="table-cell font-medium">{name}</td>
                  <td className="table-cell"><Money amount={r.gl_balance} /></td>
                  <td className="table-cell"><Money amount={r.sub_ledger_sum} /></td>
                  <td className="table-cell">
                    {r.matches ? (
                      <span className="text-accent-600 font-medium">matches</span>
                    ) : (
                      <span className="text-red-600 font-medium">diff {r.diff}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function KpiCard({
  label, value, loading,
}: { label: string; value: string | undefined; loading: boolean }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-ink-700 mb-1">{label}</div>
      <div className="text-2xl">
        {loading ? "—" : <Money amount={value} />}
      </div>
    </div>
  );
}

function PctCard({
  label, pct, loading,
}: { label: string; pct: string | undefined; loading: boolean }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-ink-700 mb-1">{label}</div>
      <div className="text-2xl money">{loading ? "—" : `${pct ?? "0.00"}%`}</div>
    </div>
  );
}
