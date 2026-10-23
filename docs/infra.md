# Infra — сервер команды

[AGENTS.md](../AGENTS.md) · [product](product.md)

Хакатон: секреты здесь можно использовать как есть. VPS выдан организаторами — **баланс/продление не наша задача**.

## Кабинет Aeza

| | |
|--|--|
| Кабинет | https://my.aeza.ru |
| Логин | `user_jiqud99epz51@hackathon.rnd` |
| Пароль кабинета | `7.d`}4nnSdNiN+TQ` |
| Услуга | https://my.aeza.ru/services/645612 |

## VPS

| | |
|--|--|
| IP | `217.144.184.232` (+ IPv6 `2a14:a084:12e3::2`) |
| SSH | `ssh root@217.144.184.232` / `root` / `M0keAeffF751` |
| ОС | Ubuntu 26.04 |
| План | MSKs-2 · 2 CPU · 4 GB · 60 GB NVMe |
| Страна | **Москва, РФ** (Aeza) |
| Каталог | `/opt/invoice-keeper` |
| Порт | **8080** → nginx (`web`), API проксируется на `/api` |
| Демо | http://217.144.184.232.sslip.io:8080 |

## Домен

Своего домена нет.

| Куда открывать | Что это |
|--|--|
| http://217.144.184.232.sslip.io:8080 | Рабочий URL. `sslip.io` резолвится в `217.144.184.232`. |
| http://217.144.184.232:8080 | Тот же сервер по IP. |
| `hack-user-jiqud9.ptr.network` | PTR VPS. A-записи нет, в браузере не открывается. Это не URL демо. |

HTTPS и свой домен — опционально позже.

## `.env` только на сервере

В git `.env` нет. CI делает `git reset --hard` и не затирает неотслеживаемый файл. Если `.env` попадёт в коммит, workflow остановится до reset.

Скопировать `.env.example` → `/opt/invoice-keeper/.env` и выставить:

```
WEB_PORT=8080
COOKIE_SECURE=false
CORS_ORIGINS=http://217.144.184.232.sslip.io:8080,http://217.144.184.232:8080
```

`COOKIE_SECURE=false`, пока сайт по HTTP: иначе браузер не сохранит куку. Пароли URL-safe, без `@ : / # $` и пробелов. Старт API сам гоняет Alembic. Том `pgdata` деплой не удаляет.

Compose публикует ещё **5432** и **8000** на `0.0.0.0`. ufw эти порты Docker не закрывает. Снаружи команде нужен 8080; привязку БД и API к `127.0.0.1` оставляем следующим заходом.

## Первый деплой руками

Один раз, до зелёного CI. Docker и Compose на сервере уже стоят. Репозиторий публичный, для `git fetch` по HTTPS токен не нужен.

```bash
ssh root@217.144.184.232
apt-get update && apt-get install -y git curl
git clone https://github.com/ArturKolozyan/hackathon.git /opt/invoice-keeper
cd /opt/invoice-keeper
cp .env.example .env
# CORS_ORIGINS, WEB_PORT, COOKIE_SECURE — блок выше
docker compose up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

Ключ Actions (на своей машине, в репозиторий не класть), тип ed25519:

```bash
ssh-keygen -t ed25519 -f deploy_ed25519 -N "" -C "github-actions-invoice-keeper"
```

Публичный `deploy_ed25519.pub` — одной строкой в `/root/.ssh/authorized_keys` (`chmod 700 /root/.ssh`, `chmod 600` на файл). Приватный файл целиком — в секрет `DEPLOY_SSH_KEY`.

Повторно без CI: `cd /opt/invoice-keeper && git fetch origin main && git reset --hard origin/main && docker compose up --build -d`.

## CI

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) — push в `main` и `workflow_dispatch`. Раннер ходит по SSH (ключ ed25519, хост сверяется по отпечатку) и на сервере делает fetch, `reset --hard origin/main`, `docker compose up --build -d`, затем `curl` на `http://127.0.0.1:8080/api/v1/health` с повторами около минуты.

GitHub → Settings → Secrets and variables → Actions:

| Secret | Что положить |
|--|--|
| `DEPLOY_HOST` | IPv4 VPS |
| `DEPLOY_USER` | SSH-пользователь с ключом в `authorized_keys` и доступом к Docker (`root`) |
| `DEPLOY_SSH_KEY` | приватный ключ ed25519, файл целиком |
| `DEPLOY_PORT` | необязательно; пусто значит `22` |

Отпечаток ed25519: `SHA256:LpmjSctDQ1eIK1qjX8VOZKRIpLpVs6k1bh6BXzPBAfg`. После переустановки VPS: `ssh-keyscan -t ed25519 217.144.184.232 | ssh-keygen -lf -` и обновить `fingerprint` в workflow.

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут (блокировка).
- IPv6 → API отвечает. Worker должен ходить на Telegram по **IPv6** (или proxy вне РФ).

Этот кусок CI Telegram не трогает.

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 плохо, IPv6 ок
- [x] Docker + Compose на VPS
- [ ] Первый деплой: клон `/opt/invoice-keeper`, свой `.env` (CORS sslip.io и IP `:8080`, `COOKIE_SECURE=false`, `WEB_PORT=8080`)
- [ ] Публичный ed25519 в `authorized_keys`; секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (`DEPLOY_PORT` по желанию)
- [ ] Зелёный workflow Deploy на push в `main`
- [ ] BotFather → токен + chat_id; `getMe` с VPS по IPv6
- [ ] (опц. позже) свой домен + HTTPS
