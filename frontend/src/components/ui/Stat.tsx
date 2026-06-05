import { cn } from "@/lib/utils";

/** Horizontal CPU/RAM usage bar with colour thresholds. */
/** Горизонтальний прогрес-бар CPU/RAM з кольоровим порогом. */
export function UsageBar({
  label,
  value,
  unit = "%",
}: {
  label: string;
  value: number | null;
  unit?: string;
}) {
  const v = value ?? 0;
  const color = v >= 90 ? "bg-crit" : v >= 75 ? "bg-warn" : "bg-accent";
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted">{label}</span>
        <span className="font-mono">{value == null ? "—" : `${v}${unit}`}</span>
      </div>
      <div className="h-1.5 rounded-full bg-panel2 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${Math.min(100, v)}%` }}
        />
      </div>
    </div>
  );
}
