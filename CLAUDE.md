# SX Monitor Server — проєктна пам'ять

> Цей файл читається Claude Code на старті кожної сесії. Тут — архітектура,
> історія робіт з безпеки, важливі інваріанти й нотатки для деплою.

## Архітектура

- **api/** — FastAPI (uvicorn). Той самий образ запускає два сервіси:
  `api` (HTTP на :8000) і `bot` (Telegram-бот, `RUN_MODE=bot`).
- **frontend/** — React + TS + Vite + Tailwind, збирається й роздається nginx'ом.
- **nginx/** — reverse-proxy (кастомний build на Alpine 3.19 з модулем
  `headers_more`), self-signed TLS. Єдиний контейнер, що публікує порти (80/443).
- **postgres** (15-alpine), **grafana** (10.4.0) — лише у внутрішній docker-мережі.
- **agent/** — Windows-агент: збирає метрики кожні 60с → `POST /api/metrics`,
  опитує чергу команд `/api/commands/pending`, виконує дії (actions.py:
  kick session, restart service, reboot, firewall block, update_agent).

**CI/CD:** push у `main` → GitHub Actions → SSH на EC2 → `docker compose up --build`.
Гілки: працюємо в `main`, дублюємо пуш у `dev` (`git push origin main:dev`).
`claude/project-migration-EPhSa` слід видалити вручну через GitHub web UI
(проксі середовища блокує `git push --delete`).

Хостинг: EC2, домен `*.compute-1.amazonaws.com` (Let's Encrypt не підтримує —
тому self-signed). Таймзона дашборду жорстко `Europe/Kyiv`.

## ВАЖЛИВІ ІНВАРІАНТИ (не зламати)

1. **nginx на Alpine 3.19 = nginx 1.24**, НЕ 1.25. Директива `http2 on;` НЕ працює —
   вмикати HTTP/2 лише через `listen 443 ssl http2;`.
2. **API-ключі агентів зберігаються як SHA-256** (`auth.py: hash_api_key`).
   Агенти шлють plaintext-ключ у `X-Api-Key` — сервер хешує й шукає за дайджестом.
   Агентам зміни НЕ потрібні. Міграція plaintext→hash робиться автоматично та
   ідемпотентно в `database.py: init_db()` (64-символьні hex пропускаються).
3. **SECRET_KEY обов'язковий** — `config.py` має валідатор, що валить старт при
   порожньому/`dev-secret`. У `.env` на EC2 має бути заданий.
4. **INTERNAL_SECRET** — окремий секрет для виклику бот→API `/api/auth/login-token`.
   Якщо не заданий, `effective_internal_secret` падає назад на `SECRET_KEY`
   (сумісність). На EC2 вже доданий.
5. **Telegram-бот авторизує всі дії** через `settings.admin_ids` — `handle_callback`,
   `/status`, `/login`. Без цього був unauthenticated RCE (бот на getUpdates
   отримує апдейти з будь-якого чату/DM).
6. Магічні login-токени зберігаються лише як SHA-256 (`security.py: _hash_token`).

## Зроблена робота з безпеки (червень 2026)

Комітами (від найновішого):
- `84b1931` Fix nginx HTTP/2 syntax для Alpine 3.19 (nginx 1.24).
- `47bafa7` Окремий INTERNAL_SECRET; хеш login-токенів; Pydantic-валідація
  payload реєстрації агента.
- `887c1ec` nginx: CSP (сувора для SPA, послаблена для Grafana subpath),
  Permissions-Policy, COOP, HTTP/2, ECDHE-only шифри, `ssl_session_tickets off`,
  `client_max_body_size 1m` + таймаути, перезапис `X-Forwarded-For` на
  `$remote_addr`. Docker: `no-new-privileges` усюди, `cap_drop: ALL` на api/bot,
  healthcheck api, non-root `appuser` у api/Dockerfile (+ `MPLCONFIGDIR`),
  frontend через `npm ci`. Grafana: вимкнено анонім/gravatar/viewer-edit,
  Secure+SameSite=strict cookies.
- `15598ca` Хешування API-ключів у БД, constant-time порівняння REGISTER_SECRET
  та X-Internal-Secret.
- `b4bacb2` Авторизація адміна для всіх команд Telegram-бота (фікс RCE).
- `0e95f8e` Code review: захист публічних endpoint'ів `require_admin`
  (`/api/servers`, `/api/status`), fail на слабкому SECRET_KEY, валідація гілки
  в update_agent, db=None фікс у фоновому таску, kick-session правильний ключ
  `session_id`, 30-денний cap на історію, null-safe backup tone, PDF timezone,
  видалення мертвого коду (14 функцій storage, start_service, cancel_reboot тощо).

### Чому так (ключові рішення)
- **Register-endpoint takeover** з аудиту виявився НЕ експлуатованим: гілка
  `if existing:` ніколи не оновлює `existing.api_key`. REGISTER_SECRET — довірений
  спільний секрет, що вводиться на хостах агентів.
- **CSP**: `script-src 'self'` безпечно для SPA (немає eval/dangerouslySetInnerHTML,
  немає iframe Grafana). Для `/grafana/` — послаблена CSP (UI Grafana вимагає
  inline/eval). Якщо PDF/графіки зламаються — додати `'unsafe-eval'` у script-src.
- **read_only rootfs НЕ ставили** — ризик зламати matplotlib/nginx temp; основний
  виграш дають cap_drop + no-new-privileges.
- **Суворі валідатори для REGISTER_SECRET/INTERNAL_SECRET НЕ додавали** — впав би
  старт при placeholder-значеннях; натомість fallback.

## Відкладені пункти безпеки (реальні, безпечні до впровадження)

1. Least-privilege роль БД для застосунку та read-only роль для Grafana
   (зараз конект під owner `monitor`).
2. Agent DPAPI: `_encrypt_dpapi` тихо повертає plaintext при помилці/не-Windows —
   зробити фатальним або голосно попереджати (agent/register_agent.py).
3. Multi-stage api build + pin образів по digest (зараз floating tags, ship gcc).
4. `python-jose` → `PyJWT` (jose застарів, має CVE-історію). `passlib` схоже
   не використовується — прибрати.
5. CSRF Origin-check на state-changing POST (значною мірою вже закрито
   SameSite=Lax — низький пріоритет).
6. TrustedHostMiddleware у main.py.

## Фічі моніторингу (червень 2026, коміт `b4c4a1d`)

Бекенд + доставка в Telegram готові; UI дашборду для них поки немає (опційний
наступний крок).

1. **Heartbeat-алерт «агент мовчить»** — `api/heartbeat.py`. Бот у `run()`-циклі
   раз на 60с (через `time.time()`, не блокує getUpdates) перевіряє `last_seen`.
   Якщо мовчить >5хв (`OFFLINE_AFTER_MIN`) → critical-алерт у топік сервера;
   при поверненні → recovery-алерт з тривалістю простою. Поважає
   `maintenance_until`. Стан у таблиці `server_heartbeats`.
2. **Прогноз заповнення дисків (ETA)** — `api/disk_forecast.py`. Лінійна регресія
   (МНК, лише stdlib) по `disk_free_*` за 48г. Показується в щоденному звіті
   («заповниться через ~3 дні» / «стабільно»). Endpoint
   `GET /api/dashboard/servers/{id}/disk-forecast`.
3. **SLA / uptime** — `api/sla.py`. Кожен перехід online↔offline пише
   `UptimeEvent`; `compute_sla()`/`compute_monthly_sla()` рахують % аптайму та
   список інцидентів. Endpoints `/api/dashboard/servers/{id}/sla?year&month` і
   `/api/dashboard/sla/summary`. Щотижневий SLA-звіт надсилається ботом у
   понеділок о 10:00 (локальний час = UTC+`report_utc_offset`).

Нові таблиці (`server_heartbeats`, `uptime_events`) створюються автоматично в
`init_db()`. Зміна `notifier.send_daily_report` зворотно-сумісна (`forecasts=None`).

Відкладений EC2-self-monitor (парсинг nginx-логів / DDoS / SSH-брутфорс) —
на паузі за рішенням користувача.

## Деплой-нотатки

- Перед деплоєм у `.env` на EC2 мають бути: `SECRET_KEY` (обов'язково),
  `DB_PASSWORD`, `GRAFANA_PASSWORD`, `REGISTER_SECRET`, `TG_BOT_TOKEN`,
  `TG_GROUP_ID`, `DASHBOARD_ADMINS`, `PUBLIC_URL=https://...`. Опціонально
  `INTERNAL_SECRET` (вже додано).
- Порт 443 має бути відкритий у AWS Security Group.
- Після деплою перевірити: дашборд відкривається (нова CSP), Grafana під
  `/grafana/`, агенти автентифікуються (міграція хешу ключів пройшла).
