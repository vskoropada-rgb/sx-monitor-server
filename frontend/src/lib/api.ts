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
  agent_version: string | null;
  agent_outdated: boolean;
  latest_agent_version: string;
}

export interface HistoryPoint {
  time: string;
  cpu?: number;
  ram?: number;
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

export interface ServerDetail {
  id: string;
  name: string;
  online: boolean;
  last_seen: string | null;
  maintenance_until: string | null;
  agent_version: string | null;
  agent_outdated: boolean;
  latest_agent_version: string;
  metrics: Record<string, any>;
  recent_alerts: Array<{ severity: string; message: string; sent_at: string | null }>;
  recent_commands: Array<{
    action: string;
    params: any;
    status: string;
    result: string | null;
    created_at: string | null;
    executed_at: string | null;
  }>;
}

export interface RdpLogEntry {
  username: string;
  ip: string | null;
  is_new_ip: boolean;
  event_time: string | null;
}

export interface RdpSessionEntry {
  username: string;
  ip: string | null;
  logon_time: string | null;
  logoff_time: string | null;
  duration_sec: number | null;
  active: boolean;
}

export interface BruteForceEntry {
  ip: string;
  attempts: number;
  usernames: string[];
  first_seen: string | null;
  last_seen: string | null;
  blocked: boolean;
}

export interface LoginLogEntry {
  id: number;
  admin_id: number;
  action: "login" | "logout";
  ip: string | null;
  user_agent: string | null;
  at: string | null;
}

export interface DiskForecast {
  path_key: string;
  current_pct: number;
  eta_hours: number | null;
  eta_str: string | null;
  rate_per_hour: number;
}

export interface SlaIncident {
  from: string;
  to: string;
  duration_min: number;
}

export interface SlaResult {
  server_id: string;
  start: string;
  end: string;
  uptime_pct: number;
  downtime_min: number;
  incidents: SlaIncident[];
}

export const api = {
  me: () => req<{ admin_id: number; authenticated: boolean }>("/api/auth/me"),
  overview: () => req<ServerOverview[]>("/api/dashboard/overview"),
  alerts: () =>
    req<{ sent: SentAlert[]; pending: PendingAlert[] }>("/api/dashboard/alerts"),
  commands: () => req<CommandEntry[]>("/api/dashboard/commands"),
  serverDetail: (id: string) => req<ServerDetail>(`/api/dashboard/servers/${id}`),
  serverHistory: (id: string, hours: number) =>
    req<HistoryPoint[]>(`/api/dashboard/servers/${id}/history?hours=${hours}`),
  serverHistoryRange: (id: string, start: string, end: string) =>
    req<HistoryPoint[]>(
      `/api/dashboard/servers/${id}/history?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    ),
  rdpLog: (id: string) => req<RdpLogEntry[]>(`/api/dashboard/servers/${id}/rdp-log`),
  rdpSessions: (id: string, days: number) =>
    req<RdpSessionEntry[]>(`/api/dashboard/servers/${id}/rdp-sessions?days=${days}`),
  authLogs: () => req<LoginLogEntry[]>("/api/dashboard/auth-logs"),
  diskForecast: (id: string) =>
    req<DiskForecast[]>(`/api/dashboard/servers/${id}/disk-forecast`),
  serverSla: (id: string, year?: number, month?: number) => {
    const p = new URLSearchParams();
    if (year)  p.set("year",  String(year));
    if (month) p.set("month", String(month));
    const qs = p.toString();
    return req<SlaResult>(`/api/dashboard/servers/${id}/sla${qs ? `?${qs}` : ""}`);
  },
  slaSummary: (year?: number, month?: number) => {
    const p = new URLSearchParams();
    if (year)  p.set("year",  String(year));
    if (month) p.set("month", String(month));
    const qs = p.toString();
    return req<SlaResult[]>(`/api/dashboard/sla/summary${qs ? `?${qs}` : ""}`);
  },
  logout: () =>
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }),
  bruteForce: (id: string, days: number) =>
    req<BruteForceEntry[]>(`/api/dashboard/servers/${id}/brute-force?days=${days}`),
  blockIp: (id: string, ip: string) =>
    fetch(`/api/dashboard/servers/${id}/block-ip`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip }),
    }),
  unblockIp: (id: string, ip: string) =>
    fetch(`/api/dashboard/servers/${id}/unblock-ip`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip }),
    }),
};
