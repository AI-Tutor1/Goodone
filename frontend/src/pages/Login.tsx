import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function Login() {
  const [username, setUsername] = useState("cfo");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: () => navigate("/", { replace: true }),
    onError: (e) => {
      if (e instanceof ApiError) {
        setErr("Invalid credentials");
      } else {
        setErr("Backend unreachable");
      }
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    login.mutate();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-50">
      <form onSubmit={onSubmit} className="card w-full max-w-sm">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-8 w-8 rounded-lg bg-accent-500" />
          <h1 className="text-base font-semibold">Tuitional Finance</h1>
        </div>
        <label className="block text-sm font-medium mb-1">Username</label>
        <input
          className="input mb-3"
          value={username}
          autoComplete="username"
          onChange={(e) => setUsername(e.target.value)}
        />
        <label className="block text-sm font-medium mb-1">Password</label>
        <input
          className="input mb-4"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {err && <div className="text-sm text-red-600 mb-3">{err}</div>}
        <button className="btn w-full" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
