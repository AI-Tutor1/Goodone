import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const NAV = [
  { to: "/", label: "Home" },
  { to: "/reports", label: "Reports" },
  { to: "/profitability", label: "Profitability" },
  { to: "/subledgers", label: "Sub-ledgers" },
  { to: "/manual-je", label: "Manual JE" },
  { to: "/sanctions", label: "Sanctions" },
  { to: "/period-close", label: "Period Close" },
  { to: "/fx", label: "FX Rates" },
  { to: "/chat", label: "Chat" },
];

export function Layout() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api.logout(),
    onSuccess: () => {
      qc.clear();
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-ink-200">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-accent-500" />
            <h1 className="text-base font-semibold">Tuitional Finance</h1>
          </div>
          <button onClick={() => logout.mutate()} className="btn-ghost">
            Sign out
          </button>
        </div>
        <nav className="max-w-7xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
                  isActive
                    ? "border-accent-500 text-accent-600"
                    : "border-transparent text-ink-700 hover:text-ink-900"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="max-w-7xl mx-auto w-full px-4 py-6 flex-1">
        <Outlet />
      </main>
      <footer className="text-xs text-ink-700 text-center py-4">
        Tuitional Finance · Phase 5 dashboard
      </footer>
    </div>
  );
}
