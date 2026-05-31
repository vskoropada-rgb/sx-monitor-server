import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso + "Z").getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}с тому`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}хв тому`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}г тому`;
  return `${Math.floor(hr / 24)}д тому`;
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
