import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Money } from "../components/Money";

export function Sanctions() {
  const qc = useQueryClient();
  const [department, setDepartment] = useState("Marketing");
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");

  const list = useQuery({ queryKey: ["sanctions"], queryFn: () => api.sanctionsList() });

  const submit = useMutation({
    mutationFn: () => api.submitSanction({ department, title, amount_aed: amount }),
    onSuccess: () => {
      setTitle("");
      setAmount("");
      qc.invalidateQueries({ queryKey: ["sanctions"] });
    },
  });

  const fa = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      api.faDecide(id, approve),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sanctions"] }),
  });

  const cfo = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      api.cfoDecide(id, approve),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sanctions"] }),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate();
  };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Sanctions</h2>

      <form onSubmit={onSubmit} className="card grid grid-cols-1 md:grid-cols-4 gap-3">
        <input className="input" placeholder="Department" value={department}
               onChange={(e) => setDepartment(e.target.value)} />
        <input className="input" placeholder="Title" value={title}
               onChange={(e) => setTitle(e.target.value)} />
        <input className="input money" placeholder="Amount AED" value={amount}
               onChange={(e) => setAmount(e.target.value)} />
        <button className="btn">Submit request</button>
      </form>

      <div className="card">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-head">#</th>
              <th className="table-head">Department</th>
              <th className="table-head">Title</th>
              <th className="table-head text-right">Amount</th>
              <th className="table-head">Status</th>
              <th className="table-head text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(list.data ?? []).map((r) => (
              <tr key={r.id}>
                <td className="table-cell font-mono text-xs">#{r.id}</td>
                <td className="table-cell">{r.department}</td>
                <td className="table-cell">{r.title}</td>
                <td className="table-cell"><Money amount={r.amount_aed} /></td>
                <td className="table-cell">{r.status}</td>
                <td className="table-cell text-right space-x-1">
                  {r.status === "PENDING_FA" && (
                    <>
                      <button onClick={() => fa.mutate({ id: r.id, approve: true })} className="btn">
                        FA approve
                      </button>
                      <button onClick={() => fa.mutate({ id: r.id, approve: false })} className="btn-ghost">
                        FA reject
                      </button>
                    </>
                  )}
                  {r.status === "PENDING_CFO" && (
                    <>
                      <button onClick={() => cfo.mutate({ id: r.id, approve: true })} className="btn">
                        CFO approve
                      </button>
                      <button onClick={() => cfo.mutate({ id: r.id, approve: false })} className="btn-ghost">
                        CFO reject
                      </button>
                    </>
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
