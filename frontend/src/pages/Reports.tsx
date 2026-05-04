import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PnL, BS, ReportLine, api } from "../api/client";
import { Money } from "../components/Money";

const TODAY = new Date().toISOString().slice(0, 10);
const THIS_MONTH = TODAY.slice(0, 7);

export function Reports() {
  const [period, setPeriod] = useState(THIS_MONTH);
  const [asOf, setAsOf] = useState(TODAY);

  const pnl = useQuery({ queryKey: ["pnl", period], queryFn: () => api.pnl(period) });
  const bs = useQuery({ queryKey: ["bs", asOf], queryFn: () => api.bs(asOf) });

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">P&amp;L and Balance Sheet</h2>

      <section className="card">
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="block text-xs font-medium mb-1">Period</label>
            <input
              className="input w-40"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="2026-04"
            />
          </div>
        </div>
        {pnl.isLoading ? (
          <div className="text-sm text-ink-700">Loading P&amp;L…</div>
        ) : pnl.data ? (
          <PnlTable pnl={pnl.data} />
        ) : (
          <div className="text-sm text-red-600">P&amp;L unavailable</div>
        )}
      </section>

      <section className="card">
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="block text-xs font-medium mb-1">As of</label>
            <input
              className="input w-44"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              placeholder="2026-04-30"
            />
          </div>
        </div>
        {bs.isLoading ? (
          <div className="text-sm text-ink-700">Loading BS…</div>
        ) : bs.data ? (
          <BsTable bs={bs.data} />
        ) : (
          <div className="text-sm text-red-600">BS unavailable</div>
        )}
      </section>
    </div>
  );
}

function PnlTable({ pnl }: { pnl: PnL }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Block title="Revenue" lines={pnl.revenue} total={pnl.revenue_total} />
      <Block title="Cost of service" lines={pnl.cost_of_service} total={pnl.cost_total} />
      <Block title="Operating expenses" lines={pnl.operating_expenses} total={pnl.opex_total} />
      <Block title="Non-operating" lines={pnl.non_operating} total={pnl.non_op_total} />
      <div className="card lg:col-span-2 bg-ink-50">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <Cell label="Gross profit" v={pnl.gross_profit} />
          <Cell label="Operating profit" v={pnl.operating_profit} />
          <Cell label="Net profit" v={pnl.net_profit} />
          <Cell label="Revenue total" v={pnl.revenue_total} />
        </div>
      </div>
    </div>
  );
}

function BsTable({ bs }: { bs: BS }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Block title="Assets" lines={bs.assets} total={bs.assets_total} />
      <Block title="Liabilities" lines={bs.liabilities} total={bs.liabilities_total} />
      <Block title="Equity" lines={bs.equity} total={bs.equity_total} />
    </div>
  );
}

function Block({
  title, lines, total,
}: { title: string; lines: ReportLine[]; total: string }) {
  return (
    <div>
      <h3 className="font-medium mb-2">{title}</h3>
      <table className="min-w-full">
        <thead>
          <tr>
            <th className="table-head">Code</th>
            <th className="table-head">Name</th>
            <th className="table-head text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.code}>
              <td className="table-cell font-mono text-xs">{l.code}</td>
              <td className="table-cell">{l.name}</td>
              <td className="table-cell"><Money amount={l.amount_aed} /></td>
            </tr>
          ))}
          <tr className="font-medium">
            <td className="table-cell" colSpan={2}>Total</td>
            <td className="table-cell"><Money amount={total} /></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Cell({ label, v }: { label: string; v: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-ink-700 mb-1">{label}</div>
      <div className="text-lg"><Money amount={v} /></div>
    </div>
  );
}
