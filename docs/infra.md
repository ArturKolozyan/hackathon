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
| Домен | нет своего. Живой URL — sslip.io, см. ниже |
| Путь | `/opt/invoice-keeper` |
| Порт приложения | **8080** (`web` / nginx). `/api` проксируется на API |

## Как открывать

| | |
|--|--|
| Живой URL | http://217.144.184.232.sslip.io:8080 |
| По IP | http://217.144.184.232:8080 |
| PTR | `hack-user-jiqud9.ptr.network` в браузере не открывается. Не URL |

sslip.io резолвится в этот IP. HTTPS и certbot — не этот кусок.

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут (блокировка).
- IPv6 → API отвечает. Клиент в `worker`, `TELEGRAM_FORCE_IPV6=true` (сокет только `::`).
- Транспорт — long polling, не webhook. Токен и chat id только в `.env` на сервере.
- Сеть bridge у Docker часто без IPv6. Деплой добавляет [compose.telegram-host.yml](../compose.telegram-host.yml): worker в сети хоста, Postgres для него — `127.0.0.1`.

## Деплой

Push в `main` и ручной `workflow_dispatch` → [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) → SSH:

```bash
cd /opt/invoice-keeper
git fetch origin main
git reset --hard origin/main
docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

`up -d` может вернуться раньше, чем nginx ответит, поэтому workflow повторяет curl около трёх минут. `.env` в git нет: `reset --hard` его не трогает, `git clean` деплой не делает. Репозиторий публичный — для `git fetch` хватает `origin` = `https://github.com/ArturKolozyan/hackathon.git`. Второй compose-файл нужен, чтобы worker видел IPv6 хоста.

Actions ходит **ключом**, не паролем из таблицы SSH.

### GitHub Secrets

В репозиторий значения не коммитить. Пароль root сюда не класть.

| Secret | Что |
|--------|-----|
| `DEPLOY_HOST` | `217.144.184.232` |
| `DEPLOY_USER` | `root`. Владеет `/opt/invoice-keeper` и может `docker` |
| `DEPLOY_SSH_KEY` | приватный ключ целиком (PEM, с `BEGIN`/`END`), без passphrase. Публичная часть — в `/root/.ssh/authorized_keys` |
| `DEPLOY_PORT` | необязательно. Пусто = 22 |

Отпечаток для деплоя — **ECDSA** `SHA256:E+eFNJNFwH/+68XXrzlY+Gtpfs/5eRKrwHFmTWL+s3c`. Он зашит в workflow. `appleboy/ssh-action` v1.2.5 не задаёт `HostKeyAlgorithms`: drone-ssh 1.8.2 (`golang.org/x/crypto` v0.45.0) предлагает `ecdsa-sha2-nistp256` раньше `ssh-ed25519`, и сервер отдаёт ECDSA. ED25519 `SHA256:LpmjSctDQ1eIK1qjX8VOZKRIpLpVs6k1bh6BXzPBAfg` подходит обычному OpenSSH, в этом Action он не совпадёт. RSA `SHA256:liIVVkDgQWnXMutSjzvkJLfc2YL77kdOVtkF0pe6cqY`. Переустановка VPS — снять отпечатки заново, иначе деплой отвергнет хост.

### Первый раз

Workflow каталог и `.env` не создаёт. Docker Compose на сервере уже есть. На хосте нужен `curl`. `WEB_PORT` оставить `8080`.

```bash
git clone https://github.com/ArturKolozyan/hackathon.git /opt/invoice-keeper
cd /opt/invoice-keeper
cp .env.example .env
docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

### Ручной деплой

```bash
ssh root@217.144.184.232
cd /opt/invoice-keeper && git fetch origin main && git reset --hard origin/main && docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

### CORS

Страница и API на одном origin (`:8080`, nginx отдаёт `/api`). Браузер CORS для живого UI не спрашивает — ни для sslip.io, ни для IP.

`CORS_ORIGINS` в серверном `.env` нужен только если API вызывают с другого origin (Vite `:5173`, прямой порт `8000`). Иначе хватает localhost из `.env.example`. Пример, если надо:

```
CORS_ORIGINS=http://217.144.184.232.sslip.io:8080,http://217.144.184.232:8080,http://localhost:5173,http://localhost:8080
```

Пока HTTP: `COOKIE_SECURE=false`.

Postgres слушает хостовый `5432`, API — `8000`. Снаружи это лишнее; этот PR порты не закрывает.

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 плохо, IPv6 ок
- [x] Docker + Compose на VPS; приложение на **8080**, не на 80/443
- [ ] Публичный ключ в `authorized_keys` и GitHub Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, опционально `DEPLOY_PORT`
- [ ] Клон в `/opt/invoice-keeper`, свой `.env` (не в git), `WEB_PORT=8080`, `curl` на хосте
- [ ] Деплой веб+api+worker, health `http://127.0.0.1:8080/api/v1/health`
- [ ] BotFather → токен + chat_id; `getMe` с VPS по IPv6
- [ ] (опц.) свой домен + DNS. PTR не использовать. HTTPS не в этом куске
