import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { severityColor, timeAgo } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Bell, BellRing } from "lucide-react";

export function AlertsPanel() {
  const { data } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts, refetchInterval: 15000 });

  const pending = data?.pending ?? [];
  const sent = data?.sent ?? [];

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex items-center gap-2">
        <BellRing className="w-4 h-4 text-warn" />
        <span className="font-semibold">Алерти</span>
        {pending.length > 0 && <Badge tone="warn">{pending.length} накопичено</Badge>}
      </CardHeader>
      <CardBody className="flex-1 overflow-y-auto scrollbar-thin space-y-2">
        {pending.map((p) => (
          <div key={`${p.server_id}-${p.alert_key}`} className="rounded-lg bg-panel2 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${severityColor(p.severity)}`}>
                {p.title}
                {p.count > 1 && <span className="text-muted"> ×{p.count}</span>}
              </span>
              <span className="text-xs text-muted">{p.server_id}</span>
            </div>
            {p.body && <p className="text-xs text-muted mt-0.5">{p.body}</p>}
          </div>
        ))}

        {sent.length > 0 && (
          <div className="pt-2 text-xs text-muted uppercase tracking-wide">Історія</div>
        )}
        {sent.map((a) => (
          <div key={a.id} className="flex items-center gap-2 text-sm px-1">
            <Bell className={`w-3.5 h-3.5 shrink-0 ${severityColor(a.severity)}`} />
            <span className="truncate flex-1">{a.message}</span>
            <span className="text-xs text-muted shrink-0">{timeAgo(a.sent_at)}</span>
          </div>
        ))}

        {pending.length === 0 && sent.length === 0 && (
          <div className="text-center text-muted text-sm py-8">Немає алертів 🎉</div>
        )}
      </CardBody>
    </Card>
  );
}
