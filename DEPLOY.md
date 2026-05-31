# Деплой на AWS EC2

## Що знадобиться

- AWS акаунт з кредитами
- Домен (або subdomain) з можливістю додати A-запис
- Telegram bot token (`@BotFather`)
- OpenAI API key

---

## Крок 1 — Запустити EC2-інстанс

1. Відкрий **AWS Console → EC2 → Launch instance**
2. Налаштуй:
   - **Name:** `sx-monitor-server`
   - **AMI:** Ubuntu Server 24.04 LTS (Free tier eligible)
   - **Instance type:** `t3.small`
   - **Key pair:** створи новий → завантажиться `.pem` файл → збережи (потрібен для SSH і CI/CD)
   - **Storage:** 20 ГБ gp3 (замість дефолтних 8 ГБ)

3. **Security group** — відкрий порти:

   | Type | Port | Source |
   |------|------|--------|
   | SSH  | 22   | My IP (або 0.0.0.0/0 тимчасово) |
   | HTTP | 80   | 0.0.0.0/0 |
   | HTTPS | 443 | 0.0.0.0/0 |

4. Натисни **Launch instance**
5. Після запуску — виділи **Elastic IP** і прив'яжи до інстансу:
   - EC2 → Elastic IPs → Allocate → Associate → вибери інстанс
   - Elastic IP поки прив'язаний до запущеного інстансу — **безкоштовний**

---

## Крок 2 — Налаштувати DNS

У свого реєстратора домену додай **A-запис**:

```
monitor.yourdomain.com  →  <Elastic IP>
```

Зміни DNS поширюються 5–30 хвилин. Перевір: `ping monitor.yourdomain.com`

---

## Крок 3 — Підключитись і запустити bootstrap

```bash
# Зміни права на ключ (macOS/Linux)
chmod 400 ~/Downloads/your-key.pem

# Підключись
ssh -i ~/Downloads/your-key.pem ubuntu@<Elastic IP>
```

На сервері:

```bash
# Swap 1 ГБ (страховка при першому білді)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# bootstrap: встановить Docker, склонує репо, створить .env
curl -fsSL https://raw.githubusercontent.com/vskoropada-rgb/sx-monitor-server/main/scripts/bootstrap.sh | sudo bash
```

Bootstrap зупиниться після `cp .env.example .env` із підказкою заповнити `.env`.

---

## Крок 4 — Заповнити .env

```bash
cd /root/sx-monitor-server   # або /home/ubuntu/sx-monitor-server
nano .env
```

Що заповнити:

```env
DB_PASSWORD=           # будь-який надійний пароль, напр: openssl rand -hex 16
TG_BOT_TOKEN=          # від @BotFather
TG_GROUP_ID=           # ID групи з темами (від'ємне число, напр -1001234567890)
OPENAI_API_KEY=        # sk-...
GRAFANA_PASSWORD=      # пароль для Grafana UI
DOMAIN=monitor.yourdomain.com
PUBLIC_URL=https://monitor.yourdomain.com
SECRET_KEY=            # openssl rand -hex 32
REGISTER_SECRET=       # openssl rand -hex 16
DASHBOARD_ADMINS=      # твій Telegram user_id (дізнатись: @userinfobot)
```

Згенерувати секрети прямо в терміналі:

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "REGISTER_SECRET=$(openssl rand -hex 16)"
echo "DB_PASSWORD=$(openssl rand -hex 16)"
```

---

## Крок 5 — Перший запуск

```bash
cd /root/sx-monitor-server
sudo docker compose up -d
```

Перший запуск займе 3–5 хвилин (білд frontend React + api Python).

Перевір статус:

```bash
sudo docker compose ps
sudo docker compose logs -f api    # логи API
```

Всі сервіси мають показати `Up` або `Up (healthy)`.

---

## Крок 6 — SSL-сертифікат (Let's Encrypt)

Після того як DNS вже вказує на сервер і порт 80 відкритий:

```bash
sudo docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d monitor.yourdomain.com \
  --email your@email.com \
  --agree-tos --no-eff-email
```

Перезапусти nginx:

```bash
sudo docker compose restart nginx
```

Сайт має відкритись по `https://monitor.yourdomain.com`.

---

## Крок 7 — GitHub Secrets (для CI/CD)

Після успішного першого запуску — підключи автодеплой при push у `main`.

Іди на GitHub → **sx-monitor-server → Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Значення |
|--------|----------|
| `SERVER_HOST` | Elastic IP (або домен) |
| `SERVER_USER` | `ubuntu` (або `root`) |
| `SERVER_SSH_KEY` | вміст `.pem` файлу цілком (від `-----BEGIN` до `-----END`) |

Тепер кожен push у `main` → автоматичний `git pull + docker compose up -d --build` на сервері.

> ⚠️ **Увага:** GitHub Actions клонує репо в `/opt/sx-monitor-server` (прописано в `deploy.yml`),
> але bootstrap.sh кладе його в `/root/` або `/home/ubuntu/`. Звіри шлях і виправ у `deploy.yml`
> або перемісти репо в `/opt/sx-monitor-server` перед увімкненням CI/CD.

---

## Крок 8 — Зареєструвати Windows-агентів

На кожному Windows-сервері (в репо `SX_Monitoring`):

1. Заповни `.env` агента:
   ```env
   API_URL=https://monitor.yourdomain.com
   REGISTER_SECRET=<той самий REGISTER_SECRET з сервера>
   SERVER_NAME=Company1
   TG_TOPIC_ID=<ID теми для цієї компанії>
   ```

2. Зареєструй:
   ```
   python register_agent.py
   ```

3. Запусти агента:
   ```
   python agent.py
   ```

---

## Корисні команди на сервері

```bash
# Статус всіх контейнерів
sudo docker compose ps

# Логи конкретного сервісу
sudo docker compose logs -f api
sudo docker compose logs -f bot

# Перезапуск після змін .env
sudo docker compose up -d

# Оновити вручну (без CI/CD)
git pull origin main && sudo docker compose up -d --build

# Бекап БД
bash scripts/backup-db.sh

# Моніторинг ресурсів
sudo docker stats
```

---

## Оцінка витрат

| Ресурс | Ціна (us-east-1) |
|--------|-----------------|
| t3.small (on-demand) | ~$15.2/міс |
| EBS gp3 20 ГБ | ~$1.6/міс |
| Elastic IP (прив'язаний) | $0 |
| Трафік (перші 100 ГБ) | $0 |
| **Разом** | **~$17/міс** |

$119.42 кредитів → **≈ 7 місяців** роботи.
