# SX Monitor Server

Центральний сервер системи моніторингу Windows-серверів 1С.

Стек: FastAPI · PostgreSQL · Telegram bot · React+Vite · Grafana · nginx · Docker Compose

---

## Гілки

| Гілка | Призначення | Auto-deploy |
|-------|------------|-------------|
| `main` | Production сервер + production агент | → Prod EC2 (при push) |
| `dev` | Dev/test сервер + dev агент | → Dev сервер (якщо увімкнено) |

### Агент (Windows-клієнт)

Код у директорії `agent/`. URL залежить від гілки:

```powershell
# Production (main)
irm "https://raw.githubusercontent.com/vskoropada-rgb/sx-monitor-server/main/agent/install.ps1" | iex

# Dev/test (dev)
irm "https://raw.githubusercontent.com/vskoropada-rgb/sx-monitor-server/dev/agent/install.ps1" | iex
```

---

## CI/CD Pipeline

```
Розробник
   │
   ├─► git push → dev ──► GitHub Actions (deploy-dev.yml)
   │                           │
   │                           └─► SSH → Dev сервер
   │                               git checkout dev && git pull
   │                               docker compose up -d --build
   │
   └─► PR: dev → main (review + merge)
               │
               └─► GitHub Actions (deploy.yml)
                       │
                       └─► SSH → Prod EC2
                           git checkout main && git pull
                           docker compose up -d --build
```

### GitHub Secrets (Settings → Secrets and variables → Actions)

**Production:**

| Secret | Значення |
|--------|----------|
| `SERVER_HOST` | IP або домен prod EC2 |
| `SERVER_USER` | `ubuntu` або `root` |
| `SERVER_SSH_KEY` | вміст `.pem` файлу |

**Dev (опційно):**

| Secret | Значення |
|--------|----------|
| `DEV_SERVER_HOST` | IP dev сервера |
| `DEV_SERVER_USER` | SSH user |
| `DEV_SERVER_SSH_KEY` | SSH ключ |

| Variable | Значення |
|----------|----------|
| `DEV_DEPLOY_ENABLED` | `true` |

> Якщо dev сервера немає — не додавай ці змінні. `deploy-dev.yml` не запуститься.

---

## Деплой на Prod EC2

Детальна інструкція: [DEPLOY.md](DEPLOY.md)

```bash
# Перший запуск на сервері
curl -fsSL https://raw.githubusercontent.com/vskoropada-rgb/sx-monitor-server/main/scripts/bootstrap.sh | bash
nano /opt/sx-monitor-server/.env
docker compose up -d
```

---

## Структура репозиторію

```
├── api/               FastAPI: endpoints, bot, analyzer, notifier, auth
├── frontend/          React + TypeScript + Tailwind: dashboard
├── nginx/             nginx.conf
├── grafana/           dashboards + provisioning
├── scripts/           bootstrap.sh, backup-db.sh, restore-db.sh
├── agent/             Windows-агент (client-server mode)
│   ├── agent.py           збір метрик + виконання команд
│   ├── register_agent.py  одноразова реєстрація на сервері
│   ├── collectors/        disk, memory, services, backup, security, rdp...
│   ├── install.ps1        one-liner інсталятор для Windows
│   ├── manage.ps1         інтерактивне меню налаштування
│   └── .env.example       шаблон конфігу агента
├── docker-compose.yml
└── .env.example       шаблон конфігу сервера
```
