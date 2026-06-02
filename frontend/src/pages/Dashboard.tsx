import { ServerCard } from "@/components/ServerCard";
import { AlertsPanel } from "@/components/AlertsPanel";
import { CommandLog } from "@/components/CommandLog";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Activity, LogOut, RefreshCw, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

export function Dashboard() {
  const { data: servers, isLoading, isFetching } = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 10000,
  });

  const { data: slaData } = useQuery({
    queryKey: ["slaSummary"],
    queryFn: () => api.slaSummary(),
    refetchInterval: 120000,
  });

  const slaMap = Object.fromEntries((slaData ?? []).map((r) => [r.server_id, r]));

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
            <Link
              to="/sla"
              className="flex items-center gap-1.5 text-sm text-muted hover:text-text transition-colors"
            >
              <TrendingUp className="w-4 h-4" /> SLA
            </Link>
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
              <ServerCard key={s.id} s={s} sla={slaMap[s.id]} />
            ))}
          </section>
        )}

        <section className="grid gap-4 lg:grid-cols-2 h-[420px]">
          <AlertsPanel />
          <CommandLog />
        </section>
      </main>
    </div>
  );
}
