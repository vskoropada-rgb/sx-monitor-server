import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { HistoryPoint } from "@/lib/api";
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
  BarChart2,
  Download,
  History,
} from "lucide-react";
import type { RdpLogEntry } from "@/lib/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

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

function chartTime(iso: string): string {
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

// ── chart section ──────────────────────────────────────────────────────────────

function MetricsChart({ serverId }: { serverId: string }) {
  const [hours, setHours] = useState<1 | 4 | 24>(1);

  const { data = [], isLoading } = useQuery({
    queryKey: ["serverHistory", serverId, hours],
    queryFn: () => api.serverHistory(serverId, hours),
    refetchInterval: 60000,
  });

  const chartData = data.map((p: HistoryPoint) => ({
    ...p,
    label: chartTime(p.time),
  }));

  const labelStep = Math.max(1, Math.floor(chartData.length / 8));
  const tickFormatter = (_: string, index: number) =>
    index % labelStep === 0 ? chartData[index]?.label ?? "" : "";

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-accent" />
          <span className="font-semibold">CPU & RAM</span>
        </div>
        <div className="flex gap-1">
          {([1, 4, 24] as const).map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={cn(
                "px-2 py-0.5 text-xs rounded",
                hours === h
                  ? "bg-accent text-bg font-semibold"
                  : "text-muted hover:text-text"
              )}
            >
              {h}г
            </button>
          ))}
        </div>
      </CardHeader>
      <CardBody>
        {isLoading ? (
          <div className="h-48 flex items-center justify-center text-muted text-sm">
            Завантаження…
          </div>
        ) : chartData.length === 0 ? (
          <EmptyNote>Даних ще немає</EmptyNote>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#6b7280" }}
                tickFormatter={tickFormatter}
                interval={0}
              />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#6b7280" }} unit="%" />
              <Tooltip
                contentStyle={{ background: "#1a1a2e", border: "1px solid #374151", borderRadius: 6 }}
                labelStyle={{ color: "#9ca3af" }}
                formatter={(val) => [`${val}%`]}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="cpu"
                name="CPU"
                stroke="#22d3ee"
                dot={false}
                strokeWidth={1.5}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ram"
                name="RAM"
                stroke="#f97316"
                dot={false}
                strokeWidth={1.5}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardBody>
    </Card>
  );
}

// ── PDF export section ─────────────────────────────────────────────────────────

function today() {
  return new Date().toISOString().slice(0, 10);
}
function weekAgo() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

function ExportSection({
  serverId,
  serverName,
  recentAlerts,
}: {
  serverId: string;
  serverName: string;
  recentAlerts: Array<{ severity: string; message: string; sent_at: string | null }>;
}) {
  const [from, setFrom] = useState(weekAgo);
  const [to, setTo] = useState(today);
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const startISO = new Date(from + "T00:00:00").toISOString();
      const endISO = new Date(to + "T23:59:59").toISOString();
      const history = await api.serverHistoryRange(serverId, startISO, endISO);

      const { default: jsPDF } = await import("jspdf");
      const { default: autoTable } = await import("jspdf-autotable");

      const doc = new jsPDF();

      doc.setFontSize(16);
      doc.text(`Звіт: ${serverName}`, 14, 18);
      doc.setFontSize(10);
      doc.setTextColor(120);
      doc.text(`Період: ${from} — ${to}`, 14, 26);
      doc.text(`Сформовано: ${new Date().toLocaleString("uk-UA")}`, 14, 32);
      doc.setTextColor(0);

      doc.setFontSize(12);
      doc.text("Метрики CPU / RAM", 14, 44);

      const tableRows = history.slice(0, 500).map((p: HistoryPoint) => [
        new Date(p.time.endsWith("Z") ? p.time : p.time + "Z").toLocaleString("uk-UA"),
        p.cpu != null ? `${p.cpu}%` : "—",
        p.ram != null ? `${p.ram}%` : "—",
      ]);

      autoTable(doc, {
        startY: 48,
        head: [["Час", "CPU", "RAM"]],
        body: tableRows.length ? tableRows : [["Немає даних", "", ""]],
        styles: { fontSize: 8 },
        headStyles: { fillColor: [30, 64, 175] },
      });

      const afterTable = (doc as any).lastAutoTable?.finalY ?? 60;

      doc.setFontSize(12);
      doc.text("Останні алерти", 14, afterTable + 12);

      const alertRows = recentAlerts.slice(0, 30).map((a) => [
        fmtDateTime(a.sent_at),
        a.severity,
        a.message,
      ]);

      autoTable(doc, {
        startY: afterTable + 16,
        head: [["Час", "Рівень", "Повідомлення"]],
        body: alertRows.length ? alertRows : [["Алертів немає", "", ""]],
        styles: { fontSize: 8 },
        headStyles: { fillColor: [30, 64, 175] },
        columnStyles: { 2: { cellWidth: "auto" } },
      });

      doc.save(`${serverName}_${from}_${to}.pdf`);
    } catch (e) {
      console.error("PDF export error:", e);
      alert("Помилка при генерації PDF");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        <Download className="w-4 h-4 text-accent" />
        <span className="font-semibold">Експорт PDF</span>
      </CardHeader>
      <CardBody>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Від
            <input
              type="date"
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
              className="bg-panel2 border border-border rounded px-2 py-1 text-text text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            До
            <input
              type="date"
              value={to}
              min={from}
              max={today()}
              onChange={(e) => setTo(e.target.value)}
              className="bg-panel2 border border-border rounded px-2 py-1 text-text text-sm"
            />
          </label>
          <button
            onClick={handleExport}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent text-bg text-sm font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            <Download className="w-3.5 h-3.5" />
            {loading ? "Генерація…" : "Завантажити PDF"}
          </button>
        </div>
      </CardBody>
    </Card>
  );
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

  const { data: rdpLog = [] } = useQuery({
    queryKey: ["rdpLog", id],
    queryFn: () => api.rdpLog(id!),
    enabled: !!id,
    refetchInterval: 60000,
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

  const cpu: number | null = m.cpu?.percent ?? null;
  const ram: number | null = m.ram?.percent ?? null;
  const ramFreeGb: number | null = m.ram?.free_gb ?? null;
  const uptime: string | null = m.uptime ?? null;
  const disks: any[] = m.disks ?? [];
  const services: any[] = m.services ?? [];
  // backup fields are at root level of metrics (merged from backup.collect())
  const backup = {
    status:          m.status          ?? m.backup?.status,
    latest_file:     m.latest_file     ?? m.backup?.file,
    latest_size_mb:  m.latest_size_mb  ?? m.backup?.size_mb,
    latest_age_hours:m.latest_age_hours?? m.backup?.age_hours,
    latest_time:     m.latest_time     ?? null,
    latest_integrity:m.latest_integrity?? null,
    issues:          m.issues          ?? m.backup?.issues ?? [],
    recent_files:    m.recent_files    ?? [],
    total_files:     m.total_files     ?? null,
    backup_path:     m.backup_path     ?? null,
  };
  const backupIssues: string[] = backup.issues ?? [];
  const activeSessions: any[] = m.active_sessions ?? [];

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

          {data.agent_version && (
            <Badge tone={data.agent_outdated ? "warn" : "muted"}>
              {data.agent_outdated ? "⬆️ " : ""}v{data.agent_version}
              {data.agent_outdated ? ` → ${data.latest_agent_version}` : ""}
            </Badge>
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

        {/* ── Section 2: Графіки CPU / RAM ─────────────────────────────────── */}
        <MetricsChart serverId={data.id} />

        {/* ── Section 3: Диски ─────────────────────────────────────────────── */}
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

        {/* ── Section 4: Сервіси ───────────────────────────────────────────── */}
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

        {/* ── Section 5: Бекапи ───────────────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Database className="w-4 h-4 text-accent" />
            <span className="font-semibold">Бекапи</span>
          </CardHeader>
          <CardBody className="space-y-3">
            {backup.status ? (
              <>
                {/* Статус + останній файл */}
                <div className="flex flex-wrap items-center gap-3">
                  <Badge tone={backupTone}>{backup.status}</Badge>
                  {backup.total_files != null && (
                    <span className="text-xs text-muted">Всього: {backup.total_files} файл(ів)</span>
                  )}
                  {backup.backup_path && (
                    <span className="font-mono text-xs text-muted truncate max-w-xs">{backup.backup_path}</span>
                  )}
                </div>

                {backupIssues.length > 0 && (
                  <ul className="space-y-1">
                    {backupIssues.map((issue: string, i: number) => (
                      <li key={i} className="flex items-start gap-1.5 text-xs text-warn">
                        <span className="mt-0.5">•</span>{issue}
                      </li>
                    ))}
                  </ul>
                )}

                {/* Список файлів */}
                {backup.recent_files.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-muted border-b border-border">
                          <th className="text-left pb-1.5 font-medium">Файл</th>
                          <th className="text-right pb-1.5 font-medium w-20">Розмір</th>
                          <th className="text-right pb-1.5 font-medium w-36">Час</th>
                          <th className="text-right pb-1.5 font-medium w-20">Вік</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {backup.recent_files.map((f: any, i: number) => (
                          <tr key={i} className={i === 0 ? "text-text" : "text-muted"}>
                            <td className="py-1.5 pr-2 font-mono truncate max-w-[200px]">{f.name}</td>
                            <td className="py-1.5 text-right">{f.size_mb} MB</td>
                            <td className="py-1.5 text-right font-mono">{f.time}</td>
                            <td className="py-1.5 text-right">{f.age_hours}г</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  backup.latest_file && (
                    <p className="text-xs text-muted">
                      Останній: <span className="text-text font-mono">{backup.latest_file}</span>
                      {backup.latest_time && <> — {backup.latest_time}</>}
                      {backup.latest_size_mb != null && <> ({backup.latest_size_mb} MB)</>}
                    </p>
                  )
                )}
              </>
            ) : (
              <EmptyNote>немає даних</EmptyNote>
            )}
          </CardBody>
        </Card>

        {/* ── Section 6: Безпека ───────────────────────────────────────────── */}
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

        {/* ── Section 7: RDP Активні сесії ────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-accent" />
            <span className="font-semibold">Активні RDP сесії</span>
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

        {/* ── Section 7b: Журнал RDP входів ───────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-accent" />
              <span className="font-semibold">Журнал RDP входів</span>
            </div>
            <span className="text-xs text-muted">{rdpLog.length} записів</span>
          </CardHeader>
          <CardBody className="p-0 max-h-72 overflow-y-auto">
            {rdpLog.length === 0 ? (
              <p className="text-sm text-muted px-4 py-3">Записів ще немає — з'являться після наступного RDP-входу</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="text-xs text-muted border-b border-border/60">
                    <th className="text-left px-4 py-2 w-36">Час</th>
                    <th className="text-left px-4 py-2">Користувач</th>
                    <th className="text-left px-4 py-2">IP</th>
                    <th className="text-left px-4 py-2 w-20">Новий IP</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {rdpLog.map((e: RdpLogEntry, i: number) => (
                    <tr key={i} className={cn("hover:bg-panel2/40", e.is_new_ip ? "bg-warn/5" : "")}>
                      <td className="px-4 py-2 text-xs text-muted whitespace-nowrap">
                        {fmtDateTime(e.event_time)}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{e.username}</td>
                      <td className="px-4 py-2 font-mono text-xs">{e.ip ?? "—"}</td>
                      <td className="px-4 py-2">
                        {e.is_new_ip && (
                          <Badge tone="warn">новий</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>

        {/* ── Section 8: Останні алерти ────────────────────────────────────── */}
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

        {/* ── Section 9: Журнал команд ─────────────────────────────────────── */}
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

        {/* ── Section 10: Експорт PDF ──────────────────────────────────────── */}
        <ExportSection
          serverId={data.id}
          serverName={data.name}
          recentAlerts={data.recent_alerts}
        />
      </main>
    </div>
  );
}
