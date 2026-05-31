# Дашборд — налаштування та безпека

Веб-панель моніторингу. Стек: **React + TypeScript + Tailwind** (фронт),
**FastAPI** (бек), авторизація — **Telegram magic-link** (без паролів і VPN).

---

## Як це працює

```
1. Відкриваєш https://monitor.domain.com/
        ▼
2. Якщо немає сесії → екран входу: «Надішли /login боту»
        ▼
3. Пишеш /login у Telegram-бот
        ▼
4. Бот перевіряє, що твій user_id у DASHBOARD_ADMINS,
   і надсилає одноразове посилання (дійсне 5 хв):
   https://monitor.domain.com/auth?token=...
        ▼
5. Переходиш → бек спалює токен, ставить httpOnly cookie (8 год)
        ▼
6. Ти в дашборді ✅
```

---

## Налаштування (`.env`)

```env
PUBLIC_URL=https://monitor.yourdomain.com   # = DOMAIN під HTTPS
DASHBOARD_ADMINS=123456789                   # свій Telegram user_id (@userinfobot)
SECRET_KEY=<openssl rand -hex 32>            # підпис JWT + внутрішній secret бота
SESSION_TTL_HOURS=8
LOGIN_TOKEN_TTL_MIN=5
```

> `DASHBOARD_ADMINS` — кома-розділений список. Можна додати кілька id.

---

## Модель безпеки

| Загроза | Захист |
|---|---|
| Хтось знає URL дашборду | Без cookie — 401, видно лише екран входу |
| Перехоплення login-токена | Одноразовий, TTL 5 хв, тільки HTTPS |
| Перебір токенів | nginx rate-limit `10 req/min` на `/auth` і `/api/auth/` |
| Сторонній пише `/login` боту | Перевірка `user_id ∈ DASHBOARD_ADMINS` |
| Виклик `/api/auth/login-token` ззовні | nginx віддає 404; endpoint лише з internal-мережі + `X-Internal-Secret` |
| Крадіжка cookie | `httpOnly`, `secure`, `samesite=lax`, TTL 8 год |
| Clickjacking / MIME | заголовки `X-Frame-Options`, `X-Content-Type-Options` |

---

## 🚨 Anti-lockout — щоб НЕ замкнути себе

Єдиний ключ до панелі — **доступ до твого Telegram**. Паролів, які можна
забути, і TOTP, який можна втратити, тут немає.

### Якщо не можеш зайти:

```
Не пускає в дашборд?
        │
        ├─ 1. Просто надішли /login боту ще раз → нове посилання
        │
        ├─ 2. Бот не відповідає → перевір контейнери:
        │       ssh server → docker compose ps
        │       docker compose restart bot api
        │
        ├─ 3. nginx/сертифікат впав → працює лише сервер по SSH:
        │       docker compose logs nginx
        │       docker compose restart nginx
        │
        └─ 4. Усе зламалось → доступ до сервера НЕ залежить від наших сервісів:
                AWS EC2 → Instance Connect / Session Manager (браузер)
                → ти завжди всередині, можеш чинити що завгодно
```

### Золоті правила

1. **SSH-доступ до сервера — це твій справжній break-glass.** Він не
   залежить від nginx, бота чи дашборду. Тримай SSH-ключ у надійному місці
   (не тільки на одному пристрої).
2. **Не вмикай вайтліст IP** на `/` поки немає впевненості — саме це
   найчастіше і замикає людей.
3. **Кілька адмінів** у `DASHBOARD_ADMINS` — якщо один акаунт недоступний,
   зайде інший.
4. Дашборд **read-only** для керування (kick/block/reboot йдуть через бота
   з підтвердженням) — навіть якщо хтось зайде, без бота нічого не зламає.

---

## Локальна розробка

```bash
# бек
cd api && uvicorn main:app --reload      # :8000

# фронт (проксі на :8000 уже в vite.config.ts)
cd frontend && npm install && npm run dev # :5173
```
