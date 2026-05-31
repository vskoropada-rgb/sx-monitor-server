import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Terminal } from "lucide-react";

const statusTone = (s: string) =>
  s === "done" ? "ok" : s === "failed" ? "crit" : s === "executing" ? "accent" : "muted";

const actionIcon: Record<string, string> = {
  block_ip: "🚫",
  kick_session: "👤",
  restart_service: "🔄",
  reboot: "🔴",
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
        {cmds.map((c) => (
          <div key={c.id} className="flex items-center gap-2 text-sm">
            <span>{actionIcon[c.action] ?? "⏳"}</span>
            <span className="font-mono text-xs">{c.action}</span>
            <span className="text-xs text-muted">{c.server_id}</span>
            <Badge tone={statusTone(c.status)} className="ml-auto">
              {c.status}
            </Badge>
            <span className="text-xs text-muted w-16 text-right shrink-0">
              {timeAgo(c.created_at)}
            </span>
          </div>
        ))}
        {cmds.length === 0 && (
          <div className="text-center text-muted text-sm py-8">Команд ще не було</div>
        )}
      </CardBody>
    </Card>
  );
}
