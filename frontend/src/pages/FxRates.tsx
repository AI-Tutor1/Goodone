import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function FxRates() {
  const qc = useQueryClient();
  const rates = useQuery({ queryKey: ["fx", "AED", "PKR"], queryFn: () => api.fxRates("AED", "PKR", 60) });
  const [date, setDate] = useState("");
  const [rate, setRate] = useState("");

  const override = useMutation({
    mutationFn: () => api.fxOverride({ date, base: "AED", quote: "PKR", rate }),
    onSuccess: () => {
      setDate("");
      setRate("");
      qc.invalidateQueries({ queryKey: ["fx"] });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    override.mutate();
  };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">FX rates AED → PKR</h2>

      <form onSubmit={onSubmit} className="card grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="input" placeholder="Date YYYY-MM-DD" value={date}
               onChange={(e) => setDate(e.target.value)} />
        <input className="input money" placeholder="Rate" value={rate}
               onChange={(e) => setRate(e.target.value)} />
        <button className="btn">Manual override</button>
      </form>

      <div className="card">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-head">Date</th>
              <th className="table-head">Rate</th>
              <th className="table-head">Source</th>
            </tr>
          </thead>
          <tbody>
            {(rates.data ?? []).map((r) => (
              <tr key={r.date + r.source}>
                <td className="table-cell font-mono">{r.date}</td>
                <td className="table-cell money">{r.rate}</td>
                <td className="table-cell">
                  {r.source === "manual" ? (
                    <span className="text-amber-700 font-medium">manual</span>
                  ) : (
                    r.source
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
