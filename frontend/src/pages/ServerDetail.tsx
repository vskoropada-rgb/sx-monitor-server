import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { HistoryPoint, SlaResult, DiskForecast } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { UsageBar } from "@/components/ui/Stat";
import { cn, diskColor } from "@/lib/utils";
import { useI18n, type StringKey } from "@/i18n";
import { LanguageToggle } from "@/components/LanguageToggle";
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
  TrendingUp,
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

function slaTone(pct: number): "ok" | "warn" | "crit" {
  if (pct >= 99.9) return "ok";
  if (pct >= 99.0) return "warn";
  return "crit";
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

// ── SLA section ───────────────────────────────────────────────────────────────

function SlaSection({ sla }: { sla: SlaResult }) {
  const { t, tn, locale, fmtDateTime, fmtDowntime } = useI18n();
  const monthLabel = new Date().toLocaleDateString(locale, {
    month: "long",
    year: "numeric",
    timeZone: "Europe/Kyiv",
  });

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-accent" />
          <span className="font-semibold">{t("sla.sectionTitle", { month: monthLabel })}</span>
        </div>
        <Badge tone={slaTone(sla.uptime_pct)}>{t("sla.uptimeBadge", { pct: sla.uptime_pct })}</Badge>
      </CardHeader>
      <CardBody className="space-y-3">
        {sla.downtime_min === 0 ? (
          <p className="text-sm text-ok">{t("sla.noDowntime")}</p>
        ) : (
          <>
            <p className="text-sm text-muted">
              {t("sla.totalDowntime")}{" "}
              <span className="text-text font-medium">{fmtDowntime(sla.downtime_min)}</span>
              {" · "}
              <span className="text-text font-medium">{tn("incidents", sla.incidents.length)}</span>
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted border-b border-border/60">
                    <th className="text-left pb-1.5 font-medium w-36">{t("sla.colStart")}</th>
                    <th className="text-left pb-1.5 font-medium w-36">{t("sla.colEnd")}</th>
                    <th className="text-right pb-1.5 font-medium w-24">{t("sla.colDuration")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {sla.incidents.map((inc, i) => (
                    <tr key={i}>
                      <td className="py-1.5 font-mono">{fmtDateTime(inc.from)}</td>
                      <td className="py-1.5 font-mono">{fmtDateTime(inc.to)}</td>
                      <td className="py-1.5 text-right text-warn">{fmtDowntime(inc.duration_min)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}

// ── chart section ──────────────────────────────────────────────────────────────

function MetricsChart({ serverId }: { serverId: string }) {
  const { t, fmtHm } = useI18n();
  const [hours, setHours] = useState<1 | 4 | 24>(1);

  const { data = [], isLoading } = useQuery({
    queryKey: ["serverHistory", serverId, hours],
    queryFn: () => api.serverHistory(serverId, hours),
    refetchInterval: 60000,
  });

  const chartData = data.map((p: HistoryPoint) => ({
    ...p,
    label: fmtHm(p.time),
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
              {t("common.hoursShort", { n: h })}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardBody>
        {isLoading ? (
          <div className="h-48 flex items-center justify-center text-muted text-sm">
            {t("common.loading")}
          </div>
        ) : chartData.length === 0 ? (
          <EmptyNote>{t("chart.noData")}</EmptyNote>
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
  disks,
  slaData,
  backup,
  diskForecasts,
}: {
  serverId: string;
  serverName: string;
  recentAlerts: Array<{ severity: string; message: string; sent_at: string | null }>;
  disks: any[];
  slaData?: SlaResult;
  backup?: {
    status?: string;
    recent_files?: Array<{ name: string; size_mb: number; age_hours: number; time: string }>;
    latest_file?: string;
    latest_time?: string;
    latest_size_mb?: number;
    total_files?: number;
  };
  diskForecasts?: DiskForecast[];
}) {
  const { t, locale, fmtDateTime, fmtDowntime } = useI18n();
  const [from, setFrom] = useState(weekAgo);
  const [to, setTo] = useState(today);
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const startISO = new Date(from + "T00:00:00+03:00").toISOString();
      const endISO   = new Date(to   + "T23:59:59+03:00").toISOString();
      const history  = await api.serverHistoryRange(serverId, startISO, endISO);

      // Sample to ≤200 points for the chart
      const MAX_PTS = 200;
      const step = Math.max(1, Math.ceil(history.length / MAX_PTS));
      const pts = history.filter((_, i) => i % step === 0);

      // Summary stats
      const cpuVals = pts.filter(p => p.cpu != null).map(p => p.cpu!);
      const ramVals = pts.filter(p => p.ram != null).map(p => p.ram!);
      const avgArr  = (a: number[]) => a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
      const avgCpu = avgArr(cpuVals);
      const maxCpu = cpuVals.length ? Math.max(...cpuVals) : null;
      const avgRam = avgArr(ramVals);
      const maxRam = ramVals.length ? Math.max(...ramVals) : null;

      // Backup files: prefer those within the selected period, fall back to most recent
      const allBackupFiles = backup?.recent_files ?? [];
      const periodStart = new Date(from + "T00:00:00");
      const periodEnd   = new Date(to   + "T23:59:59");
      const backupInPeriod = allBackupFiles.filter(f => {
        const d = new Date(f.time);
        return d >= periodStart && d <= periodEnd;
      });
      const backupRows = (backupInPeriod.length > 0 ? backupInPeriod : allBackupFiles).slice(0, 10);
      const backupLabelInPeriod = backupInPeriod.length > 0;

      const alertRows = recentAlerts.slice(0, 15);

      // ── Canvas layout ──────────────────────────────────────────────────────
      const SCALE = 2;
      const PW    = 794;
      const M     = 28;
      const CW    = PW - M * 2;
      const GAP   = 14;
      const R     = 7;   // card corner radius

      const HEADER_H = 88;
      const STATS_H  = 92;
      const CHART_H  = 270;
      const SLA_H    = slaData ? 78 : 0;
      const DISK_H   = disks.length > 0
        ? 26 + Math.min(disks.length, 6) * 32 + 8
        : 0;
      const BACKUP_H = backupRows.length > 0
        ? 26 + backupRows.length * 22 + 8
        : 0;
      const ALERT_H  = alertRows.length > 0
        ? 26 + alertRows.length * 22 + 8
        : 0;
      const FOOTER_H = 36;

      const TOTAL_H =
        M + HEADER_H + GAP
        + STATS_H + GAP
        + CHART_H + GAP
        + (SLA_H    > 0 ? SLA_H    + GAP : 0)
        + (DISK_H   > 0 ? DISK_H   + GAP : 0)
        + (BACKUP_H > 0 ? BACKUP_H + GAP : 0)
        + (ALERT_H  > 0 ? ALERT_H  + GAP : 0)
        + FOOTER_H + M;

      const canvas = document.createElement("canvas");
      canvas.width  = PW    * SCALE;
      canvas.height = TOTAL_H * SCALE;
      const ctx = canvas.getContext("2d")!;
      ctx.scale(SCALE, SCALE);

      // ── Background ─────────────────────────────────────────────────────────
      ctx.fillStyle = "#eef2f7";
      ctx.fillRect(0, 0, PW, TOTAL_H);

      let y = M;

      // ── Helpers ────────────────────────────────────────────────────────────
      function card(cx: number, cy: number, cw: number, ch: number, bg = "#ffffff") {
        ctx.beginPath();
        ctx.roundRect(cx, cy, cw, ch, R);
        ctx.fillStyle = bg;
        ctx.fill();
        ctx.strokeStyle = "#dde3ed";
        ctx.lineWidth = 0.6;
        ctx.stroke();
      }

      function secLabel(text: string, lx: number, ly: number) {
        ctx.fillStyle = "#8898aa";
        ctx.font = "bold 8.5px Arial";
        ctx.fillText(text.toUpperCase(), lx, ly);
      }

      // Area + line chart helper
      function drawAreaLine(key: "cpu" | "ram", lineC: string, fillC: string,
                            ax: number, ay: number, aw: number, ah: number) {
        if (pts.length < 2) return;
        const mapped = pts.map((p, i) => {
          const v = p[key];
          if (v == null) return null;
          return { x: ax + (i / (pts.length - 1)) * aw, y: ay + ah - (v / 100) * ah };
        });
        const valid = mapped.filter(Boolean) as { x: number; y: number }[];
        if (valid.length < 2) return;

        // Area fill
        const grad = ctx.createLinearGradient(0, ay, 0, ay + ah);
        grad.addColorStop(0, fillC);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(valid[0].x, valid[0].y);
        valid.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(valid[valid.length - 1].x, ay + ah);
        ctx.lineTo(valid[0].x, ay + ah);
        ctx.closePath();
        ctx.fill();

        // Line
        ctx.strokeStyle = lineC;
        ctx.lineWidth = 1.8;
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(valid[0].x, valid[0].y);
        valid.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.stroke();
      }

      // ── 1. Header ───────────────────────────────────────────────────────────
      ctx.beginPath();
      ctx.roundRect(M, y, CW, HEADER_H, R);
      const hGrad = ctx.createLinearGradient(M, y, M + CW, y);
      hGrad.addColorStop(0, "#0f172a");
      hGrad.addColorStop(1, "#1e3a8a");
      ctx.fillStyle = hGrad;
      ctx.fill();

      // accent bottom line
      ctx.fillStyle = "#3b82f6";
      ctx.fillRect(M, y + HEADER_H - 4, CW, 4);

      ctx.fillStyle = "rgba(255,255,255,0.25)";
      ctx.font = "bold 10px Arial";
      ctx.textAlign = "right";
      ctx.fillText("SX Monitor", M + CW - 16, y + 18);
      ctx.textAlign = "left";

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 22px Arial";
      ctx.fillText(serverName, M + 20, y + 37);

      ctx.fillStyle = "rgba(255,255,255,0.55)";
      ctx.font = "11px Arial";
      ctx.fillText(t("pdf.reportPeriod", { from, to }), M + 20, y + 56);
      ctx.fillText(
        t("pdf.generated", {
          datetime: new Date().toLocaleString(locale, { timeZone: "Europe/Kyiv" }),
          n: history.length,
        }),
        M + 20, y + 74
      );
      y += HEADER_H + GAP;

      // ── 2. Stats row (4 cards) ──────────────────────────────────────────────
      const slaColor = slaData
        ? (slaData.uptime_pct >= 99.9 ? "#16a34a" : slaData.uptime_pct >= 99 ? "#d97706" : "#dc2626")
        : "#64748b";
      const bkColor = backup?.status === "critical" ? "#dc2626"
                    : backup?.status === "warning"  ? "#d97706"
                    : backup?.latest_time           ? "#16a34a"
                    : "#64748b";

      const statItems = [
        {
          label: t("pdf.avgCpu"),
          value: avgCpu != null ? `${avgCpu.toFixed(1)}%` : "—",
          sub:   maxCpu != null ? t("pdf.peak", { pct: maxCpu.toFixed(1) }) : "",
          color: "#06b6d4",
        },
        {
          label: t("pdf.avgRam"),
          value: avgRam != null ? `${avgRam.toFixed(1)}%` : "—",
          sub:   maxRam != null ? t("pdf.peak", { pct: maxRam.toFixed(1) }) : "",
          color: "#f97316",
        },
        {
          label: t("pdf.slaUptime"),
          value: slaData ? `${slaData.uptime_pct}%` : "—",
          sub:   slaData
            ? t("pdf.slaSub", {
                inc: slaData.incidents.length,
                dt: fmtDowntime(slaData.downtime_min),
              })
            : "",
          color: slaColor,
        },
        {
          label: t("pdf.lastBackup"),
          value: backup?.latest_time ? backup.latest_time.split(" ")[0] : "—",
          sub:   backup?.latest_time
            ? `${backup.latest_time.split(" ")[1] ?? ""} · ${backup.latest_size_mb != null ? backup.latest_size_mb + " MB" : ""}`
            : "",
          color: bkColor,
        },
      ];

      const sW = (CW - 9) / 4;
      statItems.forEach((s, i) => {
        const sx = M + i * (sW + 3);
        card(sx, y, sW, STATS_H);
        // top accent strip
        ctx.beginPath();
        ctx.roundRect(sx, y, sW, 4, [R, R, 0, 0]);
        ctx.fillStyle = s.color;
        ctx.fill();

        ctx.fillStyle = "#0f172a";
        ctx.font = "bold 20px Arial";
        ctx.fillText(s.value, sx + 12, y + 42);

        ctx.fillStyle = "#475569";
        ctx.font = "10.5px Arial";
        ctx.fillText(s.label, sx + 12, y + 58);

        if (s.sub) {
          ctx.fillStyle = "#94a3b8";
          ctx.font = "8.5px Arial";
          const subMax = Math.floor(sW / 6);
          ctx.fillText(
            s.sub.length > subMax ? s.sub.slice(0, subMax - 1) + "…" : s.sub,
            sx + 12, y + 72
          );
        }
      });
      y += STATS_H + GAP;

      // ── 3. CPU / RAM Chart ─────────────────────────────────────────────────
      card(M, y, CW, CHART_H);

      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 11px Arial";
      ctx.fillText(t("pdf.chartTitle"), M + 14, y + 20);

      [
        { color: "#06b6d4", label: "CPU" },
        { color: "#f97316", label: "RAM" },
      ].forEach((l, i) => {
        const lx = M + CW - 108 + i * 52;
        ctx.fillStyle = l.color;
        ctx.fillRect(lx, y + 14, 16, 3);
        ctx.fillStyle = "#64748b";
        ctx.font = "9px Arial";
        ctx.fillText(l.label, lx + 20, y + 18);
      });

      const CAX = M + 44, CAY = y + 34, CAW = CW - 56, CAH = 194;

      // clip to chart area to prevent area overflow
      ctx.save();
      ctx.beginPath();
      ctx.rect(CAX, CAY, CAW, CAH);
      ctx.clip();
      drawAreaLine("ram", "#f97316", "rgba(249,115,22,0.22)", CAX, CAY, CAW, CAH);
      drawAreaLine("cpu", "#06b6d4", "rgba(6,182,212,0.22)",  CAX, CAY, CAW, CAH);
      ctx.restore();

      // gridlines + Y labels
      ctx.textAlign = "right";
      [0, 25, 50, 75, 100].forEach(pct => {
        const gy = CAY + CAH - (pct / 100) * CAH;
        ctx.strokeStyle = pct === 0 ? "#cbd5e1" : "#f1f5f9";
        ctx.lineWidth = pct === 0 ? 0.8 : 0.5;
        ctx.beginPath(); ctx.moveTo(CAX, gy); ctx.lineTo(CAX + CAW, gy); ctx.stroke();
        ctx.fillStyle = "#94a3b8"; ctx.font = "8px Arial";
        ctx.fillText(`${pct}%`, CAX - 4, gy + 3);
      });
      ctx.textAlign = "left";

      // X labels
      if (pts.length > 1) {
        const ticks = Math.min(7, pts.length);
        const tStep = Math.max(1, Math.floor((pts.length - 1) / (ticks - 1)));
        ctx.fillStyle = "#94a3b8"; ctx.font = "8px Arial"; ctx.textAlign = "center";
        for (let i = 0; i < pts.length; i += tStep) {
          const d = new Date(pts[i].time.endsWith("Z") ? pts[i].time : pts[i].time + "Z");
          const px = CAX + (i / (pts.length - 1)) * CAW;
          ctx.fillText(
            d.toLocaleDateString(locale, { day: "2-digit", month: "2-digit", timeZone: "Europe/Kyiv" }),
            px, CAY + CAH + 14
          );
        }
        ctx.textAlign = "left";
      }
      y += CHART_H + GAP;

      // ── 4. SLA card ─────────────────────────────────────────────────────────
      if (slaData) {
        card(M, y, CW, SLA_H);
        // left accent bar
        ctx.beginPath();
        ctx.roundRect(M, y, 4, SLA_H, [R, 0, 0, R]);
        ctx.fillStyle = slaColor;
        ctx.fill();

        ctx.fillStyle = "#0f172a";
        ctx.font = "bold 11px Arial";
        ctx.fillText(t("pdf.slaCurrentMonth"), M + 16, y + 18);

        ctx.fillStyle = slaColor;
        ctx.font = "bold 26px Arial";
        ctx.textAlign = "right";
        ctx.fillText(`${slaData.uptime_pct}%`, M + CW - 14, y + 34);
        ctx.textAlign = "left";

        ctx.fillStyle = "#64748b";
        ctx.font = "10px Arial";
        const dtStr = slaData.downtime_min > 0 ? fmtDowntime(slaData.downtime_min) : "0";
        ctx.fillText(
          t("pdf.downtimeIncidents", { dt: dtStr, n: slaData.incidents.length }),
          M + 16, y + 34
        );

        // Progress bar
        const bx = M + 16, bw = CW - 32;
        ctx.beginPath(); ctx.roundRect(bx, y + 46, bw, 7, 3.5);
        ctx.fillStyle = "#e2e8f0"; ctx.fill();
        ctx.beginPath(); ctx.roundRect(bx, y + 46, bw * (slaData.uptime_pct / 100), 7, 3.5);
        ctx.fillStyle = slaColor; ctx.fill();

        if (slaData.incidents.length > 0) {
          ctx.fillStyle = "#94a3b8"; ctx.font = "8.5px Arial";
          const incParts = slaData.incidents.slice(0, 3).map(inc =>
            `${fmtDateTime(inc.from)} (${fmtDowntime(inc.duration_min)})`
          ).join("  ·  ");
          ctx.fillText(incParts, M + 16, y + 68);
        }
        y += SLA_H + GAP;
      }

      // ── 5. Disks ─────────────────────────────────────────────────────────────
      if (disks.length > 0) {
        card(M, y, CW, DISK_H);
        secLabel(t("pdf.disksTitle"), M + 14, y + 18);
        let dy = y + 26;
        disks.slice(0, 6).forEach((d: any) => {
          const freePct: number = d.free_pct ?? 0;
          const barColor = freePct < 5 ? "#dc2626" : freePct < 10 ? "#f59e0b" : "#16a34a";
          const barX = M + 108, barW = CW - 150;

          ctx.fillStyle = "#334155"; ctx.font = "10px Arial";
          ctx.fillText(d.path ?? "?", M + 14, dy + 13);

          ctx.beginPath(); ctx.roundRect(barX, dy + 5, barW, 9, 4.5);
          ctx.fillStyle = "#e2e8f0"; ctx.fill();
          ctx.beginPath(); ctx.roundRect(barX, dy + 5, Math.max(4, barW * ((100 - freePct) / 100)), 9, 4.5);
          ctx.fillStyle = barColor; ctx.fill();

          ctx.fillStyle = "#64748b"; ctx.font = "9px Arial"; ctx.textAlign = "right";
          ctx.fillText(
            t("pdf.freeOf", { pct: freePct, free: d.free_gb ?? "—", total: d.total_gb ?? "—" }),
            M + CW - 8, dy + 13
          );
          ctx.textAlign = "left";

          // ETA hint
          const fc = diskForecasts?.find(f => f.path_key === d.path);
          if (fc?.eta_str) {
            ctx.fillStyle = "#d97706"; ctx.font = "8px Arial";
            ctx.fillText(`⏳ ${fc.eta_str}`, barX, dy + 25);
            dy += 32;
          } else {
            dy += 32;
          }
        });
        y += DISK_H + GAP;
      }

      // ── 6. Backup history ──────────────────────────────────────────────────
      if (backupRows.length > 0) {
        card(M, y, CW, BACKUP_H);
        secLabel(
          backupLabelInPeriod
            ? t("pdf.backupsPeriod", { n: backupRows.length })
            : t("pdf.backupsLatest", { n: backupRows.length }),
          M + 14, y + 18
        );
        let by = y + 26;
        backupRows.forEach((f, i) => {
          ctx.fillStyle = i % 2 === 0 ? "#f8fafc" : "#ffffff";
          ctx.fillRect(M + 8, by, CW - 16, 20);

          ctx.fillStyle = "#94a3b8"; ctx.font = "9px Arial";
          ctx.fillText(f.time, M + 14, by + 14);

          ctx.fillStyle = "#334155"; ctx.font = "9.5px Arial";
          const nameMax = 52;
          const fname = f.name.length > nameMax ? "…" + f.name.slice(-(nameMax - 1)) : f.name;
          ctx.fillText(fname, M + 138, by + 14);

          ctx.fillStyle = "#64748b"; ctx.font = "9px Arial"; ctx.textAlign = "right";
          ctx.fillText(`${f.size_mb} MB`, M + CW - 12, by + 14);
          ctx.textAlign = "left";
          by += 22;
        });
        y += BACKUP_H + GAP;
      }

      // ── 7. Alerts ─────────────────────────────────────────────────────────
      if (alertRows.length > 0) {
        card(M, y, CW, ALERT_H);
        secLabel(t("pdf.alertsTitle", { n: alertRows.length }), M + 14, y + 18);
        let ay = y + 26;
        alertRows.forEach((a, i) => {
          ctx.fillStyle = i % 2 === 0 ? "#f8fafc" : "#ffffff";
          ctx.fillRect(M + 8, ay, CW - 16, 20);

          const sevC = a.severity === "critical" ? "#dc2626"
                     : a.severity === "warning"  ? "#d97706" : "#2563eb";
          ctx.fillStyle = "#94a3b8"; ctx.font = "9px Arial";
          ctx.fillText(fmtDateTime(a.sent_at), M + 14, ay + 14);

          ctx.fillStyle = sevC; ctx.font = "bold 8.5px Arial";
          ctx.fillText(a.severity.toUpperCase(), M + 138, ay + 14);

          ctx.fillStyle = "#334155"; ctx.font = "9px Arial";
          const maxMsg = 90;
          const msg = a.message.length > maxMsg ? a.message.slice(0, maxMsg - 3) + "…" : a.message;
          ctx.fillText(msg, M + 210, ay + 14);
          ay += 22;
        });
        y += ALERT_H + GAP;
      }

      // ── 8. Footer ─────────────────────────────────────────────────────────
      ctx.fillStyle = "#94a3b8";
      ctx.font = "8.5px Arial";
      ctx.textAlign = "center";
      ctx.fillText(
        `${serverName}  ·  ${from} — ${to}  ·  SX Monitor  ·  ${new Date().toLocaleDateString(locale, { timeZone: "Europe/Kyiv" })}`,
        PW / 2, y + 22
      );
      ctx.textAlign = "left";

      // ── Build PDF ──────────────────────────────────────────────────────────
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF({ format: "a4", unit: "mm", orientation: "portrait" });

      const PDF_W = 210;
      const PDF_H = 297;
      const imgH  = (TOTAL_H / PW) * PDF_W;

      if (imgH <= PDF_H) {
        doc.addImage(canvas, "PNG", 0, 0, PDF_W, imgH);
      } else {
        const pxPerPage = Math.round((PDF_H / PDF_W) * PW * SCALE);
        let srcY = 0, page = 0;
        while (srcY < canvas.height) {
          if (page > 0) doc.addPage();
          const chunkPx = Math.min(pxPerPage, canvas.height - srcY);
          const slice = document.createElement("canvas");
          slice.width  = canvas.width;
          slice.height = chunkPx;
          slice.getContext("2d")!.drawImage(
            canvas, 0, srcY, canvas.width, chunkPx,
                    0, 0,    slice.width,  chunkPx
          );
          const sliceMM = (chunkPx / (TOTAL_H * SCALE)) * imgH;
          doc.addImage(slice, "PNG", 0, 0, PDF_W, sliceMM);
          srcY += pxPerPage; page++;
        }
      }

      doc.save(`${serverName}_${from}_${to}.pdf`);
    } catch (e) {
      console.error("PDF export error:", e);
      alert(t("pdf.error", { msg: e instanceof Error ? e.message : String(e) }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        <Download className="w-4 h-4 text-accent" />
        <span className="font-semibold">{t("export.title")}</span>
      </CardHeader>
      <CardBody>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("export.from")}
            <input
              type="date"
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
              className="bg-panel2 border border-border rounded px-2 py-1 text-text text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("export.to")}
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
            {loading ? t("export.generating") : t("export.download")}
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
  const { t, tn, timeAgo, fmtTime, fmtDateTime, fmtHm } = useI18n();

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

  const { data: diskForecasts = [] } = useQuery({
    queryKey: ["diskForecast", id],
    queryFn: () => api.diskForecast(id!),
    enabled: !!id,
    refetchInterval: 300000,
  });

  const { data: slaData } = useQuery({
    queryKey: ["serverSla", id],
    queryFn: () => api.serverSla(id!),
    enabled: !!id,
    refetchInterval: 120000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        {t("common.loading")}
      </div>
    );
  }

  if (!data || (data as any).error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-crit">
        {t("server.notFound")}
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
    backup.status === "critical" ? "crit"
    : backup.status === "warning" ? "warn"
    : backup.status === "ok" ? "ok"
    : "muted";

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
            {t("common.back")}
          </button>

          <span className="text-border">|</span>

          <span className="font-bold truncate">{data.name}</span>

          {data.online ? (
            <Badge tone="ok">
              <span className="w-1.5 h-1.5 rounded-full bg-ok animate-pulse" /> {t("common.online")}
            </Badge>
          ) : (
            <Badge tone="crit">{t("common.offline")}</Badge>
          )}

          {data.agent_version && (
            <Badge tone={data.agent_outdated ? "warn" : "muted"}>
              {data.agent_outdated ? "⬆️ " : ""}v{data.agent_version}
            </Badge>
          )}

          <span className="ml-auto flex items-center gap-1 text-xs text-muted">
            <Clock className="w-3.5 h-3.5" />
            {timeAgo(data.last_seen)}
          </span>
          <LanguageToggle />
        </div>
      </header>

      {/* ── Maintenance banner / Банер обслуговування ───────────────────────── */}
      {data.maintenance_until && (
        <div className="bg-warn/10 border-b border-warn/30 text-warn text-sm px-4 py-2 text-center">
          {t("server.maintenanceUntil", { time: fmtHm(data.maintenance_until) })}
        </div>
      )}

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* ── Section 1: Key metrics / Основні метрики ─────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-accent" />
            <span className="font-semibold">{t("metrics.title")}</span>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <UsageBar label="CPU" value={cpu} />
              <div>
                <UsageBar label="RAM" value={ram} />
                {ramFreeGb != null && (
                  <p className="text-xs text-muted mt-1">{t("metrics.freeGb", { gb: ramFreeGb })}</p>
                )}
              </div>
            </div>
            {uptime && (
              <p className="mt-4 text-xs text-muted">
                {t("metrics.uptime")}: <span className="text-text font-mono">{uptime}</span>
              </p>
            )}
          </CardBody>
        </Card>

        {/* ── Section 2: CPU / RAM charts / Графіки CPU / RAM ──────────────── */}
        <MetricsChart serverId={data.id} />

        {/* ── Section 2b: SLA this month / SLA поточного місяця ────────────── */}
        {slaData && <SlaSection sla={slaData} />}

        {/* ── Section 3: Disks / Диски ─────────────────────────────────────── */}
        {disks.length > 0 && (
          <Card>
            <CardHeader className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-accent" />
              <span className="font-semibold">{t("disks.title")}</span>
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
                        {freePct != null ? t("disks.freePct", { pct: freePct }) : "—"} ·{" "}
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

              {diskForecasts.length > 0 && (
                <div className="pt-3 mt-1 border-t border-border/40 space-y-1.5">
                  <p className="text-xs font-medium text-muted uppercase tracking-wide mb-2">
                    {t("disks.forecast")}
                  </p>
                  {diskForecasts.map((f) => (
                    <div key={f.path_key} className="flex items-center justify-between text-xs">
                      <span className="text-muted font-mono">{f.path_key}:</span>
                      {f.eta_hours != null ? (
                        <span
                          className={cn(
                            "font-medium",
                            f.eta_hours < 24
                              ? "text-crit"
                              : f.eta_hours < 72
                              ? "text-warn"
                              : "text-ok"
                          )}
                        >
                          ⏳ {t("disks.willFill", { eta: f.eta_str ?? "—" })}
                        </span>
                      ) : (
                        <span className="text-muted">{t("disks.stable")}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* ── Section 4: Services / Сервіси ────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-accent" />
            <span className="font-semibold">{t("services.title")}</span>
          </CardHeader>
          <CardBody>
            {services.length === 0 ? (
              <EmptyNote>{t("common.noData")}</EmptyNote>
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

        {/* ── Section 5: Backups / Бекапи ──────────────────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Database className="w-4 h-4 text-accent" />
            <span className="font-semibold">{t("backups.title")}</span>
          </CardHeader>
          <CardBody className="space-y-3">
            {backup.status ? (
              <>
                {/* Status + latest file / Статус + останній файл */}
                <div className="flex flex-wrap items-center gap-3">
                  <Badge tone={backupTone}>{backup.status}</Badge>
                  {backup.total_files != null && (
                    <span className="text-xs text-muted">
                      {t("backups.totalPrefix")} {tn("backupFiles", backup.total_files)}
                    </span>
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

                {/* File list / Список файлів */}
                {backup.recent_files.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-muted border-b border-border">
                          <th className="text-left pb-1.5 font-medium">{t("backups.colFile")}</th>
                          <th className="text-right pb-1.5 font-medium w-20">{t("backups.colSize")}</th>
                          <th className="text-right pb-1.5 font-medium w-36">{t("backups.colTime")}</th>
                          <th className="text-right pb-1.5 font-medium w-20">{t("backups.colAge")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {backup.recent_files.map((f: any, i: number) => (
                          <tr key={i} className={i === 0 ? "text-text" : "text-muted"}>
                            <td className="py-1.5 pr-2 font-mono truncate max-w-[200px]">{f.name}</td>
                            <td className="py-1.5 text-right">{f.size_mb} MB</td>
                            <td className="py-1.5 text-right font-mono">{f.time}</td>
                            <td className="py-1.5 text-right">{t("common.hoursShort", { n: f.age_hours })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  backup.latest_file && (
                    <p className="text-xs text-muted">
                      {t("backups.latest")}: <span className="text-text font-mono">{backup.latest_file}</span>
                      {backup.latest_time && <> — {backup.latest_time}</>}
                      {backup.latest_size_mb != null && <> ({backup.latest_size_mb} MB)</>}
                    </p>
                  )
                )}
              </>
            ) : (
              <EmptyNote>{t("common.noData")}</EmptyNote>
            )}
          </CardBody>
        </Card>

        {/* ── Section 6: Security / Безпека ────────────────────────────────── */}
        {hasSecurityData && (
          <Card>
            <CardHeader className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-crit" />
              <span className="font-semibold">{t("security.title")}</span>
            </CardHeader>
            <CardBody className="space-y-4">
              {bruteForce.length > 0 && (
                <div>
                  <SectionTitle>{t("security.failedLogins", { n: bruteForce.length })}</SectionTitle>
                  <ul className="space-y-2">
                    {bruteForce.map((a: any, i: number) => (
                      <li key={i} className="text-xs space-y-0.5">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <span className={cn("font-mono font-medium", a.is_known_network ? "text-warn" : "text-crit")}>
                            {a.ip || t("security.local")}
                          </span>
                          <span className="text-muted">{tn("attempts", a.count)}</span>
                          {a.is_known_network && (
                            <Badge tone="warn">{t("security.internalNetwork")}</Badge>
                          )}
                        </div>
                        {a.usernames?.length > 0 && (
                          <div className="text-muted pl-1">
                            {t("security.userLabel")} <span className="text-text font-medium">{a.usernames.join(", ")}</span>
                          </div>
                        )}
                        {a.workstations?.length > 0 && (
                          <div className="text-muted pl-1">
                            {t("security.deviceLabel")} <span className="text-text font-mono">{a.workstations.join(", ")}</span>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {newIps.length > 0 && (
                <div>
                  <SectionTitle>{t("security.newIps", { n: newIps.length })}</SectionTitle>
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
                  <SectionTitle>{t("security.newAdmins", { n: newAdmins.length })}</SectionTitle>
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
                  <SectionTitle>{t("security.newUsb", { n: newUsb.length })}</SectionTitle>
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
                  <SectionTitle>{t("security.blockedIps", { n: blockedIps.length })}</SectionTitle>
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

        {/* ── Section 7: Active RDP sessions / Активні RDP сесії ───────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-accent" />
            <span className="font-semibold">{t("rdp.activeTitle")}</span>
          </CardHeader>
          <CardBody>
            {activeSessions.length === 0 ? (
              <EmptyNote>{t("rdp.noActive")}</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4">{t("rdp.colUser")}</th>
                      <th className="text-left pb-2 pr-4">{t("rdp.colState")}</th>
                      <th className="text-left pb-2">{t("rdp.colSession")}</th>
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

        {/* ── Section 7b: RDP login log / Журнал RDP входів ─────────────────── */}
        <Card>
          <CardHeader className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-accent" />
              <span className="font-semibold">{t("rdp.logTitle")}</span>
            </div>
            <span className="text-xs text-muted">{tn("records", rdpLog.length)}</span>
          </CardHeader>
          <CardBody className="p-0 max-h-72 overflow-y-auto">
            {rdpLog.length === 0 ? (
              <p className="text-sm text-muted px-4 py-3">{t("rdp.logEmpty")}</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="text-xs text-muted border-b border-border/60">
                    <th className="text-left px-4 py-2 w-36">{t("rdp.colTime")}</th>
                    <th className="text-left px-4 py-2">{t("rdp.colUser")}</th>
                    <th className="text-left px-4 py-2">IP</th>
                    <th className="text-left px-4 py-2 w-20">{t("rdp.colNewIp")}</th>
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
                          <Badge tone="warn">{t("rdp.newBadge")}</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>

        {/* ── Section 8: Recent alerts / Останні алерти ────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-warn" />
            <span className="font-semibold">{t("alerts.recentTitle")}</span>
          </CardHeader>
          <CardBody>
            {recentAlerts.length === 0 ? (
              <EmptyNote>{t("alerts.none")}</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4 w-24">{t("alerts.colTime")}</th>
                      <th className="text-left pb-2 pr-4 w-24">{t("alerts.colLevel")}</th>
                      <th className="text-left pb-2">{t("alerts.colMessage")}</th>
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

        {/* ── Section 9: Command log / Журнал команд ───────────────────────── */}
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-accent" />
            <span className="font-semibold">{t("commands.title")}</span>
          </CardHeader>
          <CardBody>
            {recentCommands.length === 0 ? (
              <EmptyNote>{t("commands.none")}</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted border-b border-border/60">
                      <th className="text-left pb-2 pr-4 w-28">{t("commands.colTime")}</th>
                      <th className="text-left pb-2 pr-4 w-32">{t("commands.colAction")}</th>
                      <th className="text-left pb-2 pr-4">{t("commands.colParams")}</th>
                      <th className="text-left pb-2 pr-4 w-24">{t("commands.colStatus")}</th>
                      <th className="text-left pb-2">{t("commands.colResult")}</th>
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
                          <Badge tone={statusTone(c.status)}>
                            {["done", "failed", "executing", "pending"].includes(c.status)
                              ? t(`cmdStatus.${c.status}` as StringKey)
                              : c.status}
                          </Badge>
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

        {/* ── Section 10: PDF export / Експорт PDF ─────────────────────────── */}
        <ExportSection
          serverId={data.id}
          serverName={data.name}
          recentAlerts={data.recent_alerts}
          disks={disks}
          slaData={slaData}
          backup={backup}
          diskForecasts={diskForecasts}
        />
      </main>
    </div>
  );
}
