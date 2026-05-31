import { ServerCard } from "@/components/ServerCard";
import { AlertsPanel } from "@/components/AlertsPanel";
import { CommandLog } from "@/components/CommandLog";
import { AuthLog } from "@/components/AuthLog";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Activity, LogOut, RefreshCw } from "lucide-react";

export function Dashboard() {
  const { data: servers, isLoading, isFetching } = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 10000,
  });

  const onlineCount = servers?.filter((s) => s.online).length ?? 0;
  const total = servers?.length ?? 0;

  async function logout() {
    await api.logout();
    window.location.reload();
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 backdrop-blur bg-bg/80 border-b border-border">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Activity className="w-5 h-5 text-accent" />
            <span className="font-bold">SX Monitor</span>
            <span className="text-sm text-muted ml-2">
              {onlineCount}/{total} online
            </span>
          </div>
          <div className="flex items-center gap-3">
            <RefreshCw
              className={`w-4 h-4 text-muted ${isFetching ? "animate-spin" : ""}`}
            />
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm text-muted hover:text-text transition-colors"
            >
              <LogOut className="w-4 h-4" /> Вийти
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {isLoading ? (
          <div className="text-center text-muted py-20">Завантаження…</div>
        ) : (
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {servers?.map((s) => (
              <ServerCard key={s.id} s={s} />
            ))}
          </section>
        )}

        <section className="grid gap-4 lg:grid-cols-2 h-[420px]">
          <AlertsPanel />
          <CommandLog />
        </section>

        <section className="h-[320px]">
          <AuthLog />
        </section>
      </main>
    </div>
  );
}
