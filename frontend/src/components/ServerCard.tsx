import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { UsageBar } from "@/components/ui/Stat";
import { type ServerOverview } from "@/lib/api";
import { cn, diskColor, timeAgo } from "@/lib/utils";
import { HardDrive, Server, Clock, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

export function ServerCard({ s }: { s: ServerOverview }) {
  const backupTone =
    s.backup.status === "critical" ? "crit" : s.backup.status === "warning" ? "warn" : "ok";

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-accent" />
          <span className="font-semibold">{s.name}</span>
        </div>
        {s.online ? (
          <Badge tone="ok">
            <span className="w-1.5 h-1.5 rounded-full bg-ok animate-pulse" /> online
          </Badge>
        ) : (
          <Badge tone="crit">offline</Badge>
        )}
      </CardHeader>

      <CardBody className="flex flex-col gap-4 flex-1">
        <div className="grid grid-cols-2 gap-3">
          <UsageBar label="CPU" value={s.cpu} />
          <UsageBar label="RAM" value={s.ram} />
        </div>

        <div className="space-y-1.5">
          {s.disks.map((d) => (
            <div key={d.path} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-muted">
                <HardDrive className="w-3.5 h-3.5" /> {d.path}
              </span>
              <span className={cn("font-mono", diskColor(d.free_pct))}>
                {d.free_pct}% · {d.free_gb}GB
              </span>
            </div>
          ))}
        </div>

        {s.services.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {s.services.map((svc) => (
              <span
                key={svc.name}
                className={cn(
                  "inline-flex items-center gap-1 text-xs rounded-md px-1.5 py-0.5",
                  svc.running ? "text-ok" : "text-crit"
                )}
              >
                {svc.running ? (
                  <CheckCircle2 className="w-3 h-3" />
                ) : (
                  <XCircle className="w-3 h-3" />
                )}
                {svc.name}
              </span>
            ))}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between pt-2 border-t border-border/60 text-xs">
          <Badge tone={backupTone}>
            бекап: {s.backup.status ?? "—"}
            {s.backup.age_hours != null ? ` · ${s.backup.age_hours}г` : ""}
          </Badge>
          <span className="flex items-center gap-1 text-muted">
            <Clock className="w-3 h-3" /> {timeAgo(s.last_seen)}
          </span>
        </div>

        {s.reboot_required && (
          <div className="flex items-center gap-1.5 text-warn text-xs">
            <AlertTriangle className="w-3.5 h-3.5" /> Очікує перезавантаження
          </div>
        )}
      </CardBody>
    </Card>
  );
}
