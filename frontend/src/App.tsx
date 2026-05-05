import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Layout } from "./components/Layout";
import { api } from "./api/client";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { Reports } from "./pages/Reports";
import { Profitability } from "./pages/Profitability";
import { SubLedgers } from "./pages/SubLedgers";
import { ManualJe } from "./pages/ManualJe";
import { Sanctions } from "./pages/Sanctions";
import { PeriodClose } from "./pages/PeriodClose";
import { FxRates } from "./pages/FxRates";
import { Chat } from "./pages/Chat";
import { UploadSessions } from "./pages/UploadSessions";
import { TutorPayouts } from "./pages/TutorPayouts";
import { DataQuality } from "./pages/DataQuality";
import { LmsSync } from "./pages/LmsSync";
import { BankReconciliation } from "./pages/BankReconciliation";
import { MasterData } from "./pages/MasterData";
import { Budget } from "./pages/Budget";
import { Settings } from "./pages/Settings";

function ProtectedShell() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.me(), retry: false });
  if (me.isLoading) {
    return <div className="p-8 text-sm text-ink-700">Loading…</div>;
  }
  if (me.isError) {
    return <Navigate to="/login" replace />;
  }
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedShell />}>
        <Route index element={<Home />} />
        <Route path="reports" element={<Reports />} />
        <Route path="profitability" element={<Profitability />} />
        <Route path="subledgers" element={<SubLedgers />} />
        <Route path="manual-je" element={<ManualJe />} />
        <Route path="sanctions" element={<Sanctions />} />
        <Route path="period-close" element={<PeriodClose />} />
        <Route path="fx" element={<FxRates />} />
        <Route path="chat" element={<Chat />} />
        <Route path="upload/sessions" element={<UploadSessions />} />
        <Route path="payroll/payouts" element={<TutorPayouts />} />
        <Route path="data-quality" element={<DataQuality />} />
        <Route path="ingestion/lms" element={<LmsSync />} />
        <Route path="ingestion/bank" element={<BankReconciliation />} />
        <Route path="master-data" element={<MasterData />} />
        <Route path="budget" element={<Budget />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
