import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { UsageBar } from "@/components/ui/Stat";
import { cn, diskColor, timeAgo } from "@/lib/utils";
import {
  ArrowLeft,
  Clock,
  HardDrive,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Monitor,
  Terminal,
  Bell,
  Database,
} from "lucide-react";

// ── helpers ────────────────────────────────────────────────────────────────────

function severityTone(sev: string): "crit" | "warn" | "accent" {
  if (sev === "critical") return "crit";
  if (sev === "warning") return "warn";
  return "accent";
}

function statusTone(s: string): "ok" | "crit" | "accent" | "muted" {
  if (s === "done") return "ok";
  if (s === "failed") return "crit";
  if (s === "executing") return "accent";
  return "muted";
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function maintenanceTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
}

// ── sub-sections ───────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-semibold text-muted uppercase tracking-wide mb-3">{children}</h2>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

// ── main page ─────────────────────────────────────────────────────────────────

export function ServerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["serverDetail", id],
    queryFn: () => api.serverDetail(id!),
    enabled: !!id,
    refetchInterval: 15000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Завантаження…
      </div>
    );
  }

  if (!data || (data as any).error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-crit">
        Сервер не знайдено.
      </div>
    );
  }

  const m = data.metrics ?? {};

  // Metrics shortcuts
  const cpu: number | null = m.cpu?.percent ?? null;
  const ram: number | null = m.ram?.percent ?? null;
  const ramFreeGb: number | null = m.ram?.free_gb ?? null;
  const uptime: string | null = m.uptime ?? null;
  const disks: any[] = m.disks ?? [];
  const services: any[] = m.services ?? [];
  const backup = m.backup ?? {};
  const backupIssues: string[] = backup.issues ?? [];
  const activeSessions: any[] = m.active_sessions ?? [];

  // Security
  const bruteForce: any[] = m.brute_force_alerts ?? [];
  const newIps: any[] = m.new_ip_alerts ?? [];
  const newAdmins: any[] = m.new_admins ?? [];
  const newUsb: any[] = m.new_usb_devices ?? [];
  const blockedIps: string[] = m.blocked_ips ?? [];
  const hasSecurityData =
    bruteForce.length > 0 ||
    newIps.length > 0 ||
    newAdmins.length > 0 ||
    newUsb.length > 0 ||
    blockedIps.length > 0;

  const recentAlerts = data.recent_alerts.slice(0, 10);
  const recentCommands = data.recent_commands.slice(0, 10);

  // Backup tone
  const backupTone =
    backup.status === "critical" ? "crit" : backup.status === "warning" ? "warn" : "ok";

  return (
    <div className="min-h-screen">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 backdrop-blur bg-bg/80 border-b border-border">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center gap-3">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-1.5 text-sm text-muted hover:text-text transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Назад
          </button>

          <span className="text-border">|</span>

          <span className="font-bold truncate">{data.name}</span>

          {data.online ? (
            <Badge tone="ok">
              <span className="w-1.5 h-1.5 rounded-full bg-ok animate-pulse" /> online
            </Badge>
          ) : (
            <Badge tone="crit">offline</Badge>
          )}

          <span className="ml-auto flex items-center gap-1 text-xs text-muted">
            <Clock className="w-3.5 h-3.5" />
            {timeAgo(data.last_seen)}
          </span>
        </div>
      </header>

      {/* ── Maintenance banner ──────────────────────────────────────────────── */}
      {data.maintenance_until && (
        <div className="bg-warn/10 border-b border-warn/30 text-warn text-sm px-4 py-2 text-center">
          Обслуговування до {maintenanceTime(data.maintenance_until)}
        </div>
      )}

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* ── Section 1: Основні метрики ───────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-accent" />
            <span className="font-semibold">Основні метрики</span>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <UsageBar label="CPU" value={cpu} />
              <div>
                <UsageBar label="RAM" value={ram} />
                {ramFreeGb != null && (
                  <p className="text-xs text-muted mt-1">Вільно: {ramFreeGb} GB</p>
                )}
              </div>
            </div>
            {uptime && (
              <p className="mt-4 text-xs text-muted">
                Uptime: <span className="text-text font-mono">{uptime}</span>
              </p>
            )}
          </CardBody>
        </Card>

        {/* ── Section 2: Диски ─────────────────────────────────────────────── */}
        {disks.length > 0 && (
          <Card>
            <CardHeader className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-accent" />
              <span className="font-semibold">Диски</span>
            </CardHeader>
            <CardBody className="space-y-3">
              {disks.map((d: any) => {
                const freePct: number | null = d.free_pct ?? null;
                const color =
                  freePct == null
                    ? "bg-muted"
                    : freePct < 5
                    ? "bg-crit"
                    : freePct < 10
                    ? "bg-warn"
                    : "bg-ok";
                return (
                  <div key={d.path}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-muted">{d.path}</span>
                      <span className={cn("font-mono", diskColor(freePct))}>
                        {freePct != null ? `${freePct}% вільно` : "—"} ·{" "}
                        {d.free_gb != null ? `${d.free_gb}` : "—"} /{" "}
                        {d.total_gb != null ? `${d.total_gb} GB` : "—"}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-panel2 overflow-hidden">
                      <div
                        className={cn("h-full rounded-full transition-all", color)}
                        style={{ width: `${Math.min(100, 100 - (freePct ?? 0))}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </CardBody>
          </Card>
        )}

        {/* ── Section 3: Сервіси ───────────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-accent" />
            <span className="font-semibold">Сервіси</span>
          </CardHeader>
          <CardBody>
            {services.length === 0 ? (
              <EmptyNote>немає даних</EmptyNote>
            ) : (
              <div className="flex flex-wrap gap-2">
                {services.map((svc: any) => (
                  <span
                    key={svc.name}
                    className={cn(
                      "inline-flex items-center gap-1.5 text-sm rounded-lg border px-2.5 py-1",
                      svc.is_running ?? svc.running
                        ? "text-ok border-ok/30 bg-ok/10"
                        : "text-crit border-crit/30 bg-crit/10"
                    )}
                  >
                    {svc.is_running ?? svc.running ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5" />
                    )}
                    {svc.name}
                  </span>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* ── Section 4: Бекапи ───────────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Database className="w-4 h-4 text-accent" />
            <span className="font-semibold">Бекапи</span>
          </CardHeader>
          <CardBody className="space-y-3">
            {backup.status ? (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <Badge tone={backupTone}>{backup.status}</Badge>
                  {backup.latest_file && (
                    <span className="font-mono text-xs text-muted truncate max-w-xs">
                      {backup.latest_file}
                    </span>
                  )}
                  {backup.latest_age_hours != null && (
                    <span className="text-xs text-muted">
                      Вік: {backup.latest_age_hours}г
                    </span>
                  )}
                  {backup.latest_size_mb != null && (
                    <span className="text-xs text-muted">
                      Розмір: {backup.latest_size_mb} MB
                    </span>
                  )}
                </div>
                {backup.latest_time && (
                  <p className="text-xs text-muted">
                    Останній:&nbsp;
                    <span className="text-text font-mono">{backup.latest_time}</span>
                  </p>
                )}
                {backupIssues.length > 0 && (
                  <ul className="space-y-1">
                    {backupIssues.map((issue: string, i: number) => (
                      <li key={i} className="flex items-start gap-1.5 text-xs text-warn">
                        <span className="mt-0.5">•</span>
                        {issue}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <EmptyNote>немає даних</EmptyNote>
            )}
          </CardBody>
        </Card>

        {/* ── Section 5: Безпека ───────────────────────────────────────────── */}
        {hasSecurityData && (
          <Card>
            <CardHeader className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-crit" />
              <span className="font-semibold">Безпека</span>
            </CardHeader>
            <CardBody className="space-y-4">
              {bruteForce.length > 0 && (
                <div>
                  <SectionTitle>Brute force ({bruteForce.length})</SectionTitle>
                  <ul className="space-y-1">
                    {bruteForce.map((a: any, i: number) => (
                      <li key={i} className="text-xs text-crit font-mono">
                        {typeof a === "string" ? a : JSON.stringify(a)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {newIps.length > 0 && (
                <div>
                  <SectionTitle>Нові IP ({newIps.length})</SectionTitle>
                  <ul className="space-y-1">
                    {newIps.map((ip: any, i: number) => (
                      <li key={i} className="text-xs text-warn font-mono">
                        {typeof ip === "string" ? ip : JSON.stringify(ip)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {newAdmins.length > 0 && (
                <div>
                  <SectionTitle>Нові адміни ({newAdmins.length})</SectionTitle>
                  <ul className="space-y-1">
                    {newAdmins.map((a: any, i: number) => (
                      <li key={i} className="text-xs text-warn">
                        {typeof a === "string" ? a : JSON.stringify(a)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {newUsb.length > 0 && (
                <div>
                  <SectionTitle>Нові USB ({newUsb.length})</SectionTitle>
                  <ul className="space-y-1">
                    {newUsb.map((u: any, i: number) => (
                      <li key={i} className="text-xs text-warn">
                        {typeof u === "string" ? u : JSON.stringify(u)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {blockedIps.length > 0 && (
                <div>
                  <SectionTitle>Заблоковані IP ({blockedIps.length})</SectionTitle>
                  <div className="flex flex-wrap gap-1.5">
                    {blockedIps.map((ip: string, i: number) => (
                      <span
                        key={i}
                        className="font-mono text-xs bg-crit/10 text-crit border border-crit/30 rounded px-1.5 py-0.5"
                      >
                        {ip}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* ── Section 6: RDP Сесії ─────────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-accent" />
            <span className="font-semibold">RDP Сесії</span>
          </CardHeader>
          <CardBody>
            {activeSessions.length === 0 ? (
              <EmptyNote>Немає активних сесій</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4">Користувач</th>
                      <th className="text-left pb-2 pr-4">Стан</th>
                      <th className="text-left pb-2">Session ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {activeSessions.map((sess: any, i: number) => (
                      <tr key={i} className="text-sm">
                        <td className="py-2 pr-4 font-mono text-xs">{sess.username ?? "—"}</td>
                        <td className="py-2 pr-4">
                          <Badge tone={sess.state === "Active" ? "ok" : "muted"}>
                            {sess.state ?? "—"}
                          </Badge>
                        </td>
                        <td className="py-2 font-mono text-xs text-muted">{sess.session_id ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>

        {/* ── Section 7: Останні алерти ────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-warn" />
            <span className="font-semibold">Останні алерти</span>
          </CardHeader>
          <CardBody>
            {recentAlerts.length === 0 ? (
              <EmptyNote>Алертів немає</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4 w-24">Час</th>
                      <th className="text-left pb-2 pr-4 w-24">Рівень</th>
                      <th className="text-left pb-2">Повідомлення</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {recentAlerts.map((a, i) => (
                      <tr key={i}>
                        <td className="py-2 pr-4 text-xs text-muted whitespace-nowrap">
                          {fmtTime(a.sent_at)}
                        </td>
                        <td className="py-2 pr-4">
                          <Badge tone={severityTone(a.severity)}>{a.severity}</Badge>
                        </td>
                        <td className="py-2 text-xs text-text">{a.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>

        {/* ── Section 8: Журнал команд ─────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-accent" />
            <span className="font-semibold">Журнал команд</span>
          </CardHeader>
          <CardBody>
            {recentCommands.length === 0 ? (
              <EmptyNote>Команд ще не було</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4 w-28">Час</th>
                      <th className="text-left pb-2 pr-4 w-32">Дія</th>
                      <th className="text-left pb-2 pr-4">Параметри</th>
                      <th className="text-left pb-2 pr-4 w-24">Статус</th>
                      <th className="text-left pb-2">Результат</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {recentCommands.map((c, i) => (
                      <tr key={i}>
                        <td className="py-2 pr-4 text-xs text-muted whitespace-nowrap">
                          {fmtDateTime(c.created_at)}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs">{c.action}</td>
                        <td className="py-2 pr-4 font-mono text-xs text-muted max-w-[160px] truncate">
                          {c.params ? JSON.stringify(c.params) : "—"}
                        </td>
                        <td className="py-2 pr-4">
                          <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                        </td>
                        <td className="py-2 text-xs text-muted max-w-[200px] truncate">
                          {c.result ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </main>
    </div>
  );
}
