import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LoginLogEntry } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useI18n } from "@/i18n";
import { ShieldCheck } from "lucide-react";

function shortUA(ua: string | null): string {
  if (!ua) return "—";
  if (ua.includes("Chrome")) return "Chrome";
  if (ua.includes("Firefox")) return "Firefox";
  if (ua.includes("Safari")) return "Safari";
  if (ua.includes("Edge")) return "Edge";
  return ua.slice(0, 30);
}

export function AuthLog() {
  const { t, tn, fmtDateTime } = useI18n();
  const { data = [] } = useQuery({
    queryKey: ["authLogs"],
    queryFn: api.authLogs,
    refetchInterval: 30000,
  });

  return (
    <Card className="flex flex-col h-full overflow-hidden">
      <CardHeader className="flex items-center gap-2 shrink-0">
        <ShieldCheck className="w-4 h-4 text-accent" />
        <span className="font-semibold">{t("auth.title")}</span>
        <span className="ml-auto text-xs text-muted">{tn("records", data.length)}</span>
      </CardHeader>
      <CardBody className="overflow-y-auto flex-1 p-0">
        {data.length === 0 ? (
          <p className="text-sm text-muted px-4 py-3">{t("auth.empty")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel">
              <tr className="text-xs text-muted border-b border-border/60">
                <th className="text-left px-4 py-2 w-36">{t("auth.colTime")}</th>
                <th className="text-left px-4 py-2 w-20">{t("auth.colAction")}</th>
                <th className="text-left px-4 py-2 w-32">IP</th>
                <th className="text-left px-4 py-2">{t("auth.colBrowser")}</th>
                <th className="text-left px-4 py-2 w-24">Admin ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {data.map((e: LoginLogEntry) => (
                <tr key={e.id} className="hover:bg-panel2/40 transition-colors">
                  <td className="px-4 py-2 text-xs text-muted whitespace-nowrap">
                    {fmtDateTime(e.at)}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={e.action === "login" ? "ok" : "muted"}>
                      {e.action === "login" ? t("auth.login") : t("auth.logout")}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{e.ip ?? "—"}</td>
                  <td className="px-4 py-2 text-xs text-muted">{shortUA(e.user_agent)}</td>
                  <td className="px-4 py-2 font-mono text-xs text-muted">{e.admin_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}
