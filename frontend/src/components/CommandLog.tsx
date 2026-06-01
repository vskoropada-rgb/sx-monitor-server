import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import {
  Terminal, ShieldOff, ShieldCheck, UserX, RefreshCw,
  Power, Download, Clock, type LucideIcon,
} from "lucide-react";

const statusTone = (s: string) =>
  s === "done" ? "ok" : s === "failed" ? "crit" : s === "executing" ? "accent" : "muted";

const statusLabel: Record<string, string> = {
  done:      "виконано",
  failed:    "помилка",
  executing: "виконується",
  pending:   "очікує",
};

const actionMeta: Record<string, { icon: LucideIcon; label: string; color: string }> = {
  block_ip:        { icon: ShieldOff,    label: "Блокування IP",    color: "text-crit"   },
  unblock_ip:      { icon: ShieldCheck,  label: "Розблокування IP", color: "text-ok"     },
  kick_session:    { icon: UserX,        label: "Завершення сесії", color: "text-warn"   },
  restart_service: { icon: RefreshCw,    label: "Перезапуск сервісу", color: "text-accent" },
  reboot:          { icon: Power,        label: "Перезавантаження", color: "text-warn"   },
  update_agent:    { icon: Download,     label: "Оновлення агента", color: "text-accent" },
};

export function CommandLog() {
  const { data } = useQuery({
    queryKey: ["commands"],
    queryFn: api.commands,
    refetchInterval: 10000,
  });
  const cmds = data ?? [];

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex items-center gap-2">
        <Terminal className="w-4 h-4 text-accent" />
        <span className="font-semibold">Журнал команд</span>
      </CardHeader>
      <CardBody className="flex-1 overflow-y-auto scrollbar-thin space-y-1.5">
        {cmds.map((c) => {
          const meta = actionMeta[c.action];
          const Icon = meta?.icon ?? Clock;
          const color = meta?.color ?? "text-muted";
          const label = meta?.label ?? c.action;
          return (
            <div key={c.id} className="flex items-center gap-2 text-sm">
              <Icon className={`w-3.5 h-3.5 shrink-0 ${color}`} />
              <span className="flex-1 truncate">{label}</span>
              <span className="text-xs text-muted shrink-0">{c.server_id}</span>
              <Badge tone={statusTone(c.status)}>
                {statusLabel[c.status] ?? c.status}
              </Badge>
              <span className="text-xs text-muted w-16 text-right shrink-0">
                {timeAgo(c.created_at)}
              </span>
            </div>
          );
        })}
        {cmds.length === 0 && (
          <div className="text-center text-muted text-sm py-8">Команд ще не було</div>
        )}
      </CardBody>
    </Card>
  );
}
