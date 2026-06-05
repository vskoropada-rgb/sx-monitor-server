import { api, AuthError } from "@/lib/api";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";
import { ServerDetail } from "@/pages/ServerDetail";
import { SlaPage } from "@/pages/SlaPage";
import { useI18n } from "@/i18n";
import { useQuery } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

function AuthGate() {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        {t("common.loading")}
      </div>
    );
  }

  if (error instanceof AuthError || !data?.authenticated) {
    return <Login />;
  }

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/server/:id" element={<ServerDetail />} />
      <Route path="/sla" element={<SlaPage />} />
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthGate />
    </BrowserRouter>
  );
}
