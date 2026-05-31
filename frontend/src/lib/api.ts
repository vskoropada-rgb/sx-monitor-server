// Усі запити йдуть на той самий origin, cookie httpOnly додається браузером.

export class AuthError extends Error {}

async function req<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (res.status === 401) throw new AuthError("unauthenticated");
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface DiskInfo {
  path: string;
  free_pct: number;
  free_gb: number;
  total_gb: number;
}
export interface ServiceInfo {
  name: string;
  running: boolean;
}
export interface ServerOverview {
  id: string;
  name: string;
  online: boolean;
  last_seen: string | null;
  cpu: number | null;
  ram: number | null;
  ram_free_gb: number | null;
  disks: DiskInfo[];
  services: ServiceInfo[];
  backup: {
    status: string | null;
    file: string | null;
    age_hours: number | null;
    size_mb: number | null;
  };
  reboot_required: boolean;
}

export interface SentAlert {
  id: number;
  server_id: string;
  alert_key: string;
  severity: string;
  message: string;
  sent_at: string | null;
}
export interface PendingAlert {
  server_id: string;
  alert_key: string;
  title: string;
  body: string;
  severity: string;
  count: number;
  updated_at: string | null;
}
export interface CommandEntry {
  id: number;
  server_id: string;
  action: string;
  params: Record<string, unknown> | null;
  status: string;
  result: string | null;
  created_at: string | null;
  executed_at: string | null;
}

export const api = {
  me: () => req<{ admin_id: number; authenticated: boolean }>("/api/auth/me"),
  overview: () => req<ServerOverview[]>("/api/dashboard/overview"),
  alerts: () =>
    req<{ sent: SentAlert[]; pending: PendingAlert[] }>("/api/dashboard/alerts"),
  commands: () => req<CommandEntry[]>("/api/dashboard/commands"),
  logout: () =>
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }),
};
