// Ukrainian dictionary — source of truth for translation keys.
// Український словник — джерело істини для ключів перекладу.
//
// `strings` — plain messages with optional {placeholders}.
// `strings` — звичайні повідомлення з опційними {змінними}.
// `plurals` — count-aware forms (one / few / many) resolved at runtime.
// `plurals` — форми за кількістю (один / кілька / багато), обираються в рантаймі.

export const ukStrings = {
  // ── Common / Загальне ────────────────────────────────────────────────
  "common.loading": "Завантаження…",
  "common.back": "Назад",
  "common.logout": "Вийти",
  "common.noData": "немає даних",
  "common.online": "online",
  "common.offline": "offline",
  "common.hoursShort": "{n}г",

  // ── Dashboard / Дашборд ──────────────────────────────────────────────
  "dashboard.onlineOf": "{online}/{total} online",

  // ── Login / Вхід ─────────────────────────────────────────────────────
  "login.subtitle": "Панель моніторингу серверів",
  "login.viaTelegram": "Вхід через Telegram",
  "login.step1": "Відкрийте бота в Telegram",
  "login.step2": "Надішліть команду",
  "login.step3": "Перейдіть за отриманим посиланням",
  "login.note":
    "Посилання діє 5 хвилин і працює лише один раз. Доступ мають тільки адміністратори.",

  // ── Server header / Шапка сервера ────────────────────────────────────
  "server.rebootRequired": "Очікує перезавантаження",
  "server.backup": "бекап",
  "server.maintenanceUntil": "Обслуговування до {time}",
  "server.notFound": "Сервер не знайдено.",

  // ── Key metrics / Основні метрики ────────────────────────────────────
  "metrics.title": "Основні метрики",
  "metrics.freeGb": "Вільно: {gb} GB",
  "metrics.uptime": "Uptime",
  "metrics.cpuRam": "CPU та RAM",

  // ── Disks / Диски ────────────────────────────────────────────────────
  "disks.title": "Диски",
  "disks.freePct": "{pct}% вільно",
  "disks.forecast": "Прогноз заповнення",
  "disks.willFill": "заповниться через {eta}",
  "disks.stable": "стабільно",

  // ── Services / Сервіси ───────────────────────────────────────────────
  "services.title": "Сервіси",

  // ── Backups / Бекапи ─────────────────────────────────────────────────
  "backups.title": "Бекапи",
  "backups.totalPrefix": "Всього:",
  "backups.colFile": "Файл",
  "backups.colSize": "Розмір",
  "backups.colTime": "Час",
  "backups.colAge": "Вік",
  "backups.latest": "Останній",

  // ── Security / Безпека ───────────────────────────────────────────────
  "security.title": "Безпека",
  "security.failedLogins": "Невдалі входи ({n})",
  "security.newIps": "Нові IP ({n})",
  "security.newAdmins": "Нові адміни ({n})",
  "security.newUsb": "Нові USB ({n})",
  "security.blockedIps": "Заблоковані IP ({n})",
  "security.internalNetwork": "внутр. мережа",
  "security.local": "локальний",
  "security.userLabel": "Користувач:",
  "security.deviceLabel": "Пристрій:",

  // ── RDP / RDP ────────────────────────────────────────────────────────
  "rdp.activeTitle": "Активні RDP сесії",
  "rdp.noActive": "Немає активних сесій",
  "rdp.colUser": "Користувач",
  "rdp.colState": "Стан",
  "rdp.colSession": "Session ID",
  "rdp.logTitle": "Журнал RDP входів",
  "rdp.logEmpty": "Записів ще немає — з'являться після наступного RDP-входу",
  "rdp.colTime": "Час",
  "rdp.colNewIp": "Новий IP",
  "rdp.newBadge": "новий",

  // ── Сесії користувачів / User sessions ───────────────────────────────
  "sessions.title": "Сесії користувачів",
  "sessions.empty": "Сесій за обраний період немає",
  "sessions.colUser": "Користувач",
  "sessions.colConnect": "Підключення",
  "sessions.colDisconnect": "Відключення",
  "sessions.colDuration": "Тривалість",
  "sessions.active": "активна",
  "sessions.periodToday": "Сьогодні",
  "sessions.period7d": "7 днів",
  "sessions.period30d": "30 днів",

  // ── Alerts / Алерти ──────────────────────────────────────────────────
  "alerts.recentTitle": "Останні алерти",
  "alerts.none": "Алертів немає",
  "alerts.colTime": "Час",
  "alerts.colLevel": "Рівень",
  "alerts.colMessage": "Повідомлення",
  "alerts.panelTitle": "Алерти",
  "alerts.history": "Історія",
  "alerts.noneCheer": "Немає алертів 🎉",

  // ── Commands / Команди ───────────────────────────────────────────────
  "commands.title": "Журнал команд",
  "commands.none": "Команд ще не було",
  "commands.colTime": "Час",
  "commands.colAction": "Дія",
  "commands.colParams": "Параметри",
  "commands.colStatus": "Статус",
  "commands.colResult": "Результат",
  "cmdStatus.done": "виконано",
  "cmdStatus.failed": "помилка",
  "cmdStatus.executing": "виконується",
  "cmdStatus.pending": "очікує",
  "cmdAction.block_ip": "Блокування IP",
  "cmdAction.unblock_ip": "Розблокування IP",
  "cmdAction.kick_session": "Завершення сесії",
  "cmdAction.restart_service": "Перезапуск сервісу",
  "cmdAction.reboot": "Перезавантаження",
  "cmdAction.update_agent": "Оновлення агента",

  // ── SLA / SLA ────────────────────────────────────────────────────────
  "sla.sectionTitle": "SLA — {month}",
  "sla.uptimeBadge": "{pct}% uptime",
  "sla.noDowntime": "Простоїв не зафіксовано",
  "sla.totalDowntime": "Сумарний простій:",
  "sla.colStart": "Початок",
  "sla.colEnd": "Кінець",
  "sla.colDuration": "Тривалість",
  "sla.currentMonth": "SLA поточного місяця",
  "sla.pageTitle": "SLA / Uptime",
  "sla.average": "середнє {pct}%",
  "sla.noMonthData": "Немає даних за цей місяць",
  "sla.downtimeLabel": "Простій:",
  "sla.incidentsLabel": "Інциденти:",

  // ── Auth log / Журнал авторизацій ────────────────────────────────────
  "auth.title": "Журнал авторизацій",
  "auth.empty": "Входів ще не було",
  "auth.colTime": "Час",
  "auth.colAction": "Дія",
  "auth.colBrowser": "Браузер",
  "auth.login": "вхід",
  "auth.logout": "вихід",

  // ── PDF export / Експорт PDF ─────────────────────────────────────────
  "export.title": "Експорт PDF",
  "export.from": "Від",
  "export.to": "До",
  "export.download": "Завантажити PDF",
  "export.generating": "Генерація…",
  "chart.noData": "Даних ще немає",
  "pdf.reportPeriod": "Звітний період: {from} — {to}",
  "pdf.generated": "Сформовано: {datetime}  ·  {n} точок даних",
  "pdf.avgCpu": "Середній CPU",
  "pdf.avgRam": "Середній RAM",
  "pdf.peak": "пік {pct}%",
  "pdf.slaUptime": "SLA / Uptime",
  "pdf.slaSub": "{inc} інц. · {dt} простою",
  "pdf.lastBackup": "Останній бекап",
  "pdf.chartTitle": "CPU та RAM (%)",
  "pdf.slaCurrentMonth": "SLA поточного місяця",
  "pdf.downtimeIncidents": "Простій: {dt}  ·  Інциденти: {n}",
  "pdf.disksTitle": "Стан дисків",
  "pdf.freeOf": "{pct}% вільно  ·  {free}/{total} GB",
  "pdf.backupsPeriod": "Резервні копії за звітний період ({n})",
  "pdf.backupsLatest": "Останні резервні копії ({n})",
  "pdf.alertsTitle": "Останні алерти ({n})",
  "pdf.error": "Помилка при генерації PDF: {msg}",
} as const;

export const ukPlurals = {
  records: { one: "{n} запис", few: "{n} записи", many: "{n} записів" },
  attempts: { one: "{n} спроба", few: "{n} спроби", many: "{n} спроб" },
  incidents: { one: "{n} інцидент", few: "{n} інциденти", many: "{n} інцидентів" },
  incidentsShort: { one: "{n} інц.", few: "{n} інц.", many: "{n} інц." },
  backupFiles: { one: "{n} файл", few: "{n} файли", many: "{n} файлів" },
  pending: { one: "{n} накопичено", few: "{n} накопичено", many: "{n} накопичено" },
} as const;
