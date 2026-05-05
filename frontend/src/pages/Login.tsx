import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";

export function Login() {
  const [username, setUsername] = useState("cfo");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const navigate = useNavigate();

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: (result) => {
      if ("requires_totp" in result && result.requires_totp) {
        setPendingToken(result.pending_token);
      } else {
        navigate("/", { replace: true });
      }
    },
    onError: (e) => {
      setErr(e instanceof ApiError ? "Invalid credentials" : "Backend unreachable");
    },
  });

  const totp = useMutation({
    mutationFn: () => api.verifyTotp(pendingToken!, otpCode),
    onSuccess: () => navigate("/", { replace: true }),
    onError: (e) => {
      setErr(e instanceof ApiError ? "Invalid OTP code" : "Backend unreachable");
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (pendingToken) {
      totp.mutate();
    } else {
      login.mutate();
    }
  };

  const isPending = login.isPending || totp.isPending;

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-50">
      <form onSubmit={onSubmit} className="card w-full max-w-sm">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-8 w-8 rounded-lg bg-accent-500" />
          <h1 className="text-base font-semibold">Tuitional Finance</h1>
        </div>

        {!pendingToken ? (
          <>
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
          </>
        ) : (
          <>
            <p className="text-sm text-ink-700 mb-3">
              Enter the 6-digit code from your authenticator app.
            </p>
            <label className="block text-sm font-medium mb-1">OTP Code</label>
            <input
              className="input mb-4 font-mono tracking-widest"
              value={otpCode}
              maxLength={6}
              autoFocus
              autoComplete="one-time-code"
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
            />
          </>
        )}

        {err && <div className="text-sm text-red-600 mb-3">{err}</div>}
        <button className="btn w-full" disabled={isPending}>
          {isPending ? "Verifying…" : pendingToken ? "Verify OTP" : "Sign in"}
        </button>
        {pendingToken && (
          <button
            type="button"
            className="btn-ghost w-full mt-2 text-sm"
            onClick={() => { setPendingToken(null); setOtpCode(""); setErr(null); }}
          >
            Back to login
          </button>
        )}
      </form>
    </div>
  );
}
