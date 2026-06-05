import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type SlaResult, type ServerOverview } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LanguageToggle } from "@/components/LanguageToggle";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";
import { ArrowLeft, TrendingUp, ChevronDown, ChevronUp } from "lucide-react";

function slaTone(pct: number): "ok" | "warn" | "crit" {
  if (pct >= 99.9) return "ok";
  if (pct >= 99.0) return "warn";
  return "crit";
}

function uptimePctBar({ pct }: { pct: number }) {
  const tone = slaTone(pct);
  const color =
    tone === "ok" ? "bg-ok" : tone === "warn" ? "bg-warn" : "bg-crit";
  return (
    <div className="h-1.5 rounded-full bg-panel2 overflow-hidden w-full">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ServerSlaCard({ sla, name }: { sla: SlaResult; name: string }) {
  const { t, tn, fmtDateTime, fmtDowntime } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const tone = slaTone(sla.uptime_pct);

  return (
    <Card>
      <CardHeader>
        <div
          className="flex items-center justify-between cursor-pointer select-none"
          onClick={() => sla.incidents.length > 0 && setExpanded((v) => !v)}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold truncate">{name}</span>
            {sla.incidents.length > 0 && (
              <span className="text-xs text-muted">
                {tn("incidentsShort", sla.incidents.length)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge tone={tone}>{sla.uptime_pct}%</Badge>
            {sla.incidents.length > 0 && (
              expanded
                ? <ChevronUp className="w-4 h-4 text-muted" />
                : <ChevronDown className="w-4 h-4 text-muted" />
            )}
          </div>
        </div>
      </CardHeader>

      <CardBody className="pt-0 space-y-3">
        <div className="flex items-center gap-3 text-xs text-muted">
          <span>
            {t("sla.downtimeLabel")}{" "}
            <span className={sla.downtime_min > 0 ? "text-warn font-medium" : "text-ok font-medium"}>
              {sla.downtime_min > 0 ? fmtDowntime(sla.downtime_min) : "0"}
            </span>
          </span>
          <span>·</span>
          <span>
            {t("sla.incidentsLabel")}{" "}
            <span className={sla.incidents.length > 0 ? "text-warn font-medium" : "text-ok font-medium"}>
              {sla.incidents.length}
            </span>
          </span>
        </div>

        {uptimePctBar({ pct: sla.uptime_pct })}

        {expanded && sla.incidents.length > 0 && (
          <div className="overflow-x-auto pt-2">
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
                    <td className="py-1.5 text-right text-warn font-medium">
                      {fmtDowntime(inc.duration_min)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function SlaPage() {
  const navigate = useNavigate();
  const { t, locale } = useI18n();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const { data: slaList = [], isLoading: slaLoading } = useQuery({
    queryKey: ["slaSummary", year, month],
    queryFn: () => api.slaSummary(year, month),
    refetchInterval: 120000,
  });

  const { data: servers = [] } = useQuery<ServerOverview[]>({
    queryKey: ["overview"],
    queryFn: api.overview,
    staleTime: 30000,
  });

  const nameMap = Object.fromEntries(servers.map((s) => [s.id, s.name]));

  const avgUptime =
    slaList.length > 0
      ? slaList.reduce((s, r) => s + r.uptime_pct, 0) / slaList.length
      : null;

  const monthLabel = new Date(year, month - 1, 1).toLocaleDateString(locale, {
    month: "long",
    year: "numeric",
  });

  function prevMonth() {
    if (month === 1) { setYear((y) => y - 1); setMonth(12); }
    else setMonth((m) => m - 1);
  }
  function nextMonth() {
    const nextM = month === 12 ? 1 : month + 1;
    const nextY = month === 12 ? year + 1 : year;
    if (nextY > now.getFullYear() || (nextY === now.getFullYear() && nextM > now.getMonth() + 1)) return;
    setMonth(nextM);
    setYear(nextY);
  }

  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;

  return (
    <div className="min-h-screen">
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
          <TrendingUp className="w-4 h-4 text-accent" />
          <span className="font-bold">{t("sla.pageTitle")}</span>

          {avgUptime != null && (
            <Badge tone={slaTone(avgUptime)} className="ml-2">
              {t("sla.average", { pct: avgUptime.toFixed(2) })}
            </Badge>
          )}
          <LanguageToggle className="ml-auto" />
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Month picker / Вибір місяця */}
        <div className="flex items-center gap-3">
          <button
            onClick={prevMonth}
            className="px-3 py-1.5 text-sm text-muted hover:text-text border border-border rounded transition-colors"
          >
            ‹
          </button>
          <span className="text-sm font-medium capitalize min-w-[160px] text-center">
            {monthLabel}
          </span>
          <button
            onClick={nextMonth}
            disabled={isCurrentMonth}
            className="px-3 py-1.5 text-sm text-muted hover:text-text border border-border rounded transition-colors disabled:opacity-30"
          >
            ›
          </button>
        </div>

        {slaLoading ? (
          <div className="text-center text-muted py-20">{t("common.loading")}</div>
        ) : slaList.length === 0 ? (
          <div className="text-center text-muted py-20">{t("sla.noMonthData")}</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {slaList.map((r) => (
              <ServerSlaCard
                key={r.server_id}
                sla={r}
                name={nameMap[r.server_id] ?? r.server_id}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
