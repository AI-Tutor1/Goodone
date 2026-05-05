import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

type Tab = "students" | "tutors" | "enrollments";

export function MasterData() {
  const [tab, setTab] = useState<Tab>("students");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Master Data</h2>
        <div className="flex gap-1">
          {(["students", "tutors", "enrollments"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={tab === t ? "btn" : "btn-ghost"}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>
      {tab === "students" && <StudentsPanel />}
      {tab === "tutors" && <TutorsPanel />}
      {tab === "enrollments" && <EnrollmentsPanel />}
    </div>
  );
}

// ----- Students -----

function StudentsPanel() {
  const qc = useQueryClient();
  const [displayId, setDisplayId] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const list = useQuery({ queryKey: ["students"], queryFn: () => api.listStudents() });

  const create = useMutation({
    mutationFn: () => api.createStudent(displayId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["students"] });
      setDisplayId(""); setName(""); setErr(null);
    },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Add Student</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Display ID</label>
            <input className="input" value={displayId} onChange={(e) => setDisplayId(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        </div>
        {err && <div className="text-sm text-red-600">{err}</div>}
        <button
          className="btn"
          disabled={!displayId || !name || create.isPending}
          onClick={() => create.mutate()}
        >
          Add
        </button>
      </div>
      <div className="card">
        {list.isLoading ? (
          <div className="text-sm text-ink-700">Loading…</div>
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["ID", "Display ID", "Name", "Active"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(list.data?.students ?? []).map((s) => (
                <tr key={s.student_id}>
                  <td className="table-cell font-mono">{s.student_id}</td>
                  <td className="table-cell font-mono">{s.display_id}</td>
                  <td className="table-cell">{s.name}</td>
                  <td className="table-cell">{s.active ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ----- Tutors -----

function TutorsPanel() {
  const qc = useQueryClient();
  const [displayId, setDisplayId] = useState("");
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("PKR");
  const [err, setErr] = useState<string | null>(null);

  const list = useQuery({ queryKey: ["tutors"], queryFn: () => api.listTutors() });

  const create = useMutation({
    mutationFn: () => api.createTutor(displayId, name, currency),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tutors"] });
      setDisplayId(""); setName(""); setErr(null);
    },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Add Tutor</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Display ID</label>
            <input className="input" value={displayId} onChange={(e) => setDisplayId(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Currency</label>
            <select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="PKR">PKR</option>
              <option value="AED">AED</option>
            </select>
          </div>
        </div>
        {err && <div className="text-sm text-red-600">{err}</div>}
        <button
          className="btn"
          disabled={!displayId || !name || create.isPending}
          onClick={() => create.mutate()}
        >
          Add
        </button>
      </div>
      <div className="card">
        {list.isLoading ? (
          <div className="text-sm text-ink-700">Loading…</div>
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["ID", "Display ID", "Name", "Currency", "Active"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(list.data?.tutors ?? []).map((t) => (
                <tr key={t.tutor_id}>
                  <td className="table-cell font-mono">{t.tutor_id}</td>
                  <td className="table-cell font-mono">{t.display_id}</td>
                  <td className="table-cell">{t.name}</td>
                  <td className="table-cell">{t.payment_currency}</td>
                  <td className="table-cell">{t.active ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ----- Enrollments -----

function EnrollmentsPanel() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    student_id: "", tutor_id: "", subject: "", rate_aed: "", start_date: "", status: "active",
  });
  const [err, setErr] = useState<string | null>(null);

  const list = useQuery({ queryKey: ["enrollments"], queryFn: () => api.listEnrollments() });

  const create = useMutation({
    mutationFn: () =>
      api.createEnrollment({
        student_id: Number(form.student_id),
        tutor_id: Number(form.tutor_id),
        subject: form.subject,
        rate_aed: form.rate_aed,
        start_date: form.start_date,
        status: form.status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["enrollments"] });
      setForm({ student_id: "", tutor_id: "", subject: "", rate_aed: "", start_date: "", status: "active" });
      setErr(null);
    },
    onError: (e) => setErr(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const f = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((cur) => ({ ...cur, [k]: e.target.value }));

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Add Enrollment</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {(["student_id", "tutor_id", "subject", "rate_aed", "start_date"] as const).map((k) => (
            <div key={k}>
              <label className="block text-xs font-medium mb-1 capitalize">{k.replace("_", " ")}</label>
              <input
                className="input"
                type={k === "start_date" ? "date" : "text"}
                value={form[k]}
                onChange={f(k)}
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium mb-1">Status</label>
            <select className="input" value={form.status} onChange={f("status")}>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="ended">Ended</option>
            </select>
          </div>
        </div>
        {err && <div className="text-sm text-red-600">{err}</div>}
        <button
          className="btn"
          disabled={!form.student_id || !form.tutor_id || !form.subject || create.isPending}
          onClick={() => create.mutate()}
        >
          Add
        </button>
      </div>
      <div className="card overflow-x-auto">
        {list.isLoading ? (
          <div className="text-sm text-ink-700">Loading…</div>
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                {["#", "Student", "Tutor", "Subject", "Rate AED", "Start", "Status"].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(list.data?.enrollments ?? []).map((e) => (
                <tr key={e.enrollment_id}>
                  <td className="table-cell font-mono">{e.enrollment_id}</td>
                  <td className="table-cell">{e.student_name}</td>
                  <td className="table-cell">{e.tutor_name}</td>
                  <td className="table-cell">{e.subject}</td>
                  <td className="table-cell font-mono text-right">{e.rate_aed}</td>
                  <td className="table-cell">{e.start_date}</td>
                  <td className="table-cell">{e.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
