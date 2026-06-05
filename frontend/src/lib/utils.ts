import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function severityColor(sev: string): string {
  switch (sev) {
    case "critical":
      return "text-crit";
    case "warning":
      return "text-warn";
    default:
      return "text-accent";
  }
}

export function diskColor(pct: number | null | undefined): string {
  if (pct == null) return "text-muted";
  if (pct < 5) return "text-crit";
  if (pct < 10) return "text-warn";
  return "text-ok";
}
