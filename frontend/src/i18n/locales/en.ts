// English dictionary. Typed against the Ukrainian source so a missing key
// fails the build — there can be no silent translation gaps.
// Англійський словник. Типізований за українським джерелом: пропущений ключ
// валить білд — мовчазних прогалин у перекладі бути не може.

import type { PluralForms } from "../index";
import type { ukStrings, ukPlurals } from "./uk";

export const enStrings: Record<keyof typeof ukStrings, string> = {
  // ── Common ───────────────────────────────────────────────────────────
  "common.loading": "Loading…",
  "common.back": "Back",
  "common.logout": "Log out",
  "common.noData": "no data",
  "common.online": "online",
  "common.offline": "offline",
  "common.hoursShort": "{n}h",

  // ── Dashboard ────────────────────────────────────────────────────────
  "dashboard.onlineOf": "{online}/{total} online",

  // ── Login ────────────────────────────────────────────────────────────
  "login.subtitle": "Server monitoring dashboard",
  "login.viaTelegram": "Sign in via Telegram",
  "login.step1": "Open the bot in Telegram",
  "login.step2": "Send the command",
  "login.step3": "Follow the link you receive",
  "login.note":
    "The link is valid for 5 minutes and can be used only once. Access is restricted to administrators.",

  // ── Server header ────────────────────────────────────────────────────
  "server.rebootRequired": "Reboot required",
  "server.backup": "backup",
  "server.maintenanceUntil": "Maintenance until {time}",
  "server.notFound": "Server not found.",

  // ── Key metrics ──────────────────────────────────────────────────────
  "metrics.title": "Key metrics",
  "metrics.freeGb": "Free: {gb} GB",
  "metrics.uptime": "Uptime",
  "metrics.cpuRam": "CPU & RAM",

  // ── Disks ────────────────────────────────────────────────────────────
  "disks.title": "Disks",
  "disks.freePct": "{pct}% free",
  "disks.forecast": "Fill forecast",
  "disks.willFill": "fills up in {eta}",
  "disks.stable": "stable",

  // ── Services ─────────────────────────────────────────────────────────
  "services.title": "Services",

  // ── Backups ──────────────────────────────────────────────────────────
  "backups.title": "Backups",
  "backups.totalPrefix": "Total:",
  "backups.colFile": "File",
  "backups.colSize": "Size",
  "backups.colTime": "Time",
  "backups.colAge": "Age",
  "backups.latest": "Latest",

  // ── Security ─────────────────────────────────────────────────────────
  "security.title": "Security",
  "security.failedLogins": "Failed logins ({n})",
  "security.newIps": "New IPs ({n})",
  "security.newAdmins": "New admins ({n})",
  "security.newUsb": "New USB ({n})",
  "security.blockedIps": "Blocked IPs ({n})",
  "security.internalNetwork": "internal network",
  "security.local": "local",
  "security.userLabel": "User:",
  "security.deviceLabel": "Device:",

  // ── RDP ──────────────────────────────────────────────────────────────
  "rdp.activeTitle": "Active RDP sessions",
  "rdp.noActive": "No active sessions",
  "rdp.colUser": "User",
  "rdp.colState": "State",
  "rdp.colSession": "Session ID",
  "rdp.logTitle": "RDP login log",
  "rdp.logEmpty": "No records yet — they'll appear after the next RDP login",
  "rdp.colTime": "Time",
  "rdp.colNewIp": "New IP",
  "rdp.newBadge": "new",

  // ── User sessions ────────────────────────────────────────────────────
  "sessions.title": "User sessions",
  "sessions.empty": "No sessions in the selected period",
  "sessions.colUser": "User",
  "sessions.colConnect": "Connected",
  "sessions.colDisconnect": "Disconnected",
  "sessions.colDuration": "Duration",
  "sessions.active": "active",
  "sessions.periodToday": "Today",
  "sessions.period7d": "7 days",
  "sessions.period30d": "30 days",

  // ── Brute-force audit ────────────────────────────────────────────────
  "brute.title": "Password brute-force attempts",
  "brute.empty": "No brute-force attempts recorded",
  "brute.colIp": "IP",
  "brute.colAttempts": "Attempts",
  "brute.colUsers": "Logins",
  "brute.colLastSeen": "Last seen",
  "brute.colStatus": "Status",
  "brute.blocked": "blocked",
  "brute.notBlocked": "not blocked",
  "brute.block": "Block",
  "brute.unblock": "Unblock",
  "brute.blocking": "…",

  // ── Alerts ───────────────────────────────────────────────────────────
  "alerts.recentTitle": "Recent alerts",
  "alerts.none": "No alerts",
  "alerts.colTime": "Time",
  "alerts.colLevel": "Level",
  "alerts.colMessage": "Message",
  "alerts.panelTitle": "Alerts",
  "alerts.history": "History",
  "alerts.noneCheer": "No alerts 🎉",

  // ── Commands ─────────────────────────────────────────────────────────
  "commands.title": "Command log",
  "commands.none": "No commands yet",
  "commands.colTime": "Time",
  "commands.colAction": "Action",
  "commands.colParams": "Parameters",
  "commands.colStatus": "Status",
  "commands.colResult": "Result",
  "cmdStatus.done": "done",
  "cmdStatus.failed": "failed",
  "cmdStatus.executing": "executing",
  "cmdStatus.pending": "pending",
  "cmdAction.block_ip": "Block IP",
  "cmdAction.unblock_ip": "Unblock IP",
  "cmdAction.kick_session": "Kick session",
  "cmdAction.restart_service": "Restart service",
  "cmdAction.reboot": "Reboot",
  "cmdAction.update_agent": "Update agent",

  // ── SLA ──────────────────────────────────────────────────────────────
  "sla.sectionTitle": "SLA — {month}",
  "sla.uptimeBadge": "{pct}% uptime",
  "sla.noDowntime": "No downtime recorded",
  "sla.totalDowntime": "Total downtime:",
  "sla.colStart": "Start",
  "sla.colEnd": "End",
  "sla.colDuration": "Duration",
  "sla.currentMonth": "SLA this month",
  "sla.pageTitle": "SLA / Uptime",
  "sla.average": "average {pct}%",
  "sla.noMonthData": "No data for this month",
  "sla.downtimeLabel": "Downtime:",
  "sla.incidentsLabel": "Incidents:",

  // ── Auth log ─────────────────────────────────────────────────────────
  "auth.title": "Authorization log",
  "auth.empty": "No logins yet",
  "auth.colTime": "Time",
  "auth.colAction": "Action",
  "auth.colBrowser": "Browser",
  "auth.login": "sign in",
  "auth.logout": "sign out",

  // ── PDF export ───────────────────────────────────────────────────────
  "export.title": "Export PDF",
  "export.from": "From",
  "export.to": "To",
  "export.download": "Download PDF",
  "export.generating": "Generating…",
  "chart.noData": "No data yet",
  "pdf.reportPeriod": "Reporting period: {from} — {to}",
  "pdf.generated": "Generated: {datetime}  ·  {n} data points",
  "pdf.avgCpu": "Average CPU",
  "pdf.avgRam": "Average RAM",
  "pdf.peak": "peak {pct}%",
  "pdf.slaUptime": "SLA / Uptime",
  "pdf.slaSub": "{inc} inc. · {dt} downtime",
  "pdf.lastBackup": "Latest backup",
  "pdf.chartTitle": "CPU & RAM (%)",
  "pdf.slaCurrentMonth": "SLA this month",
  "pdf.downtimeIncidents": "Downtime: {dt}  ·  Incidents: {n}",
  "pdf.disksTitle": "Disk status",
  "pdf.freeOf": "{pct}% free  ·  {free}/{total} GB",
  "pdf.backupsPeriod": "Backups in reporting period ({n})",
  "pdf.backupsLatest": "Latest backups ({n})",
  "pdf.alertsTitle": "Recent alerts ({n})",
  "pdf.error": "PDF generation error: {msg}",
};

export const enPlurals: Record<keyof typeof ukPlurals, PluralForms> = {
  records: { one: "{n} record", few: "{n} records", many: "{n} records" },
  attempts: { one: "{n} attempt", few: "{n} attempts", many: "{n} attempts" },
  incidents: { one: "{n} incident", few: "{n} incidents", many: "{n} incidents" },
  incidentsShort: { one: "{n} inc.", few: "{n} inc.", many: "{n} inc." },
  backupFiles: { one: "{n} file", few: "{n} files", many: "{n} files" },
  pending: { one: "{n} pending", few: "{n} pending", many: "{n} pending" },
};
