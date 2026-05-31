import { api, AuthError } from "@/lib/api";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";
import { useQuery } from "@tanstack/react-query";

export default function App() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Завантаження…
      </div>
    );
  }

  if (error instanceof AuthError || !data?.authenticated) {
    return <Login />;
  }

  return <Dashboard />;
}
