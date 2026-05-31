import { cn } from "@/lib/utils";
import { type ReactNode } from "react";

type Tone = "ok" | "warn" | "crit" | "muted" | "accent";

const tones: Record<Tone, string> = {
  ok: "bg-ok/15 text-ok border-ok/30",
  warn: "bg-warn/15 text-warn border-warn/30",
  crit: "bg-crit/15 text-crit border-crit/30",
  muted: "bg-muted/15 text-muted border-muted/30",
  accent: "bg-accent/15 text-accent border-accent/30",
};

export function Badge({
  tone = "muted",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
