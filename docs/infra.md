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
| Домен | `rekeeper.ru` (Beget). Живой URL — https://rekeeper.ru |
| Путь | `/opt/invoice-keeper` |
| Публичные порты | **80** и **443** (Caddy). `443/udp` — HTTP/3, без него сайт жив |
| Авария | nginx только на `127.0.0.1:8080` самого VPS. В интернет 8080 не открыт |

## Домен и HTTPS

Caddy (`caddy:2.11.7-alpine`) сам берёт сертификат Let's Encrypt и проксирует `rekeeper.ru`, `www.rekeeper.ru` на сервис `web:80` в сети compose. Certbot не используем. Сертификаты лежат в томе `caddy_data`. `docker compose down -v` их сотрёт, следующий запуск снова упрётся в лимит Let's Encrypt.

На **2026-10-23** публичные `1.1.1.1` и `8.8.8.8` отвечают **NXDOMAIN** на `rekeeper.ru` и `www.rekeeper.ru` (SOA зоны `.ru`). Записи в панели Beget наружу ещё не делегированы. Пока `dig` не показывает A `217.144.184.232`, браузер домен не откроет и сертификат не выпустится. Код второго прохода не ждёт: когда A появятся, Caddy доберёт сертификат сам.

```bash
dig +short @1.1.1.1 rekeeper.ru A
dig +short @1.1.1.1 www.rekeeper.ru A
dig +short @1.1.1.1 rekeeper.ru AAAA
dig +short @8.8.8.8 rekeeper.ru A
dig +short @8.8.8.8 www.rekeeper.ru A
```

Нужно с публичного резолвера, не из панели:

- A `@` → `217.144.184.232`
- A `www` → `217.144.184.232`
- AAAA нет, **или** AAAA `@` и `www` равен `2a14:a084:12e3::2`. Чужой AAAA (парковка) ломает ACME: Let's Encrypt ходит и по IPv6
- Снаружи открыты 80/tcp и 443/tcp. Если в панели Aeza включён фаервол — пустить их. 443/udp желателен для HTTP/3
- PTR `hack-user-jiqud9.ptr.network` не URL

Оба имени в одном блоке Caddyfile. Выпуск идёт по каждому имени отдельно: если в DNS есть только одно, второе останется без сертификата, первое Caddy всё равно добирает.

## Как открывать

| | |
|--|--|
| Сайт | https://rekeeper.ru |
| С www | https://www.rekeeper.ru |
| На самом VPS | http://127.0.0.1:8080 — только loopback, для curl и SSH-туннеля |
| PTR | не URL |

Локально: http://localhost:8080. Там Caddy тоже стартует и в логе будут ошибки ACME — сертификат выпустится только на этом VPS.

## Порты

| Куда | Кто |
|------|-----|
| 80, 443/tcp, 443/udp | Caddy → `web:80` |
| 127.0.0.1:8080 | nginx. Авария и health деплоя |
| 127.0.0.1:8000 | API мимо nginx |
| 127.0.0.1:5432 | Postgres |

Раньше API и Postgres слушали `0.0.0.0`. Проверки внутри контейнеров ходят сами в себя: API на `127.0.0.1:8000`, `pg_isready` в `db`. Привязка к loopback хоста их не ломает.

На VPS не задавать `CADDY_HTTP_PORT` / `CADDY_HTTPS_PORT`. Иначе ACME стучится на 80, а Caddy слушает другой хостовый порт.

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут (блокировка).
- IPv6 → API отвечает. Worker должен ходить на Telegram по **IPv6** (или proxy вне РФ).

Следующий кусок, не этот деплой.

## Деплой

Push в `main` и ручной `workflow_dispatch` → [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) → SSH:

```bash
cd /opt/invoice-keeper
git fetch origin main
git reset --hard origin/main
docker compose up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: rekeeper.ru' http://127.0.0.1/
```

Первый curl — nginx и API, нужен 200. Второй — Caddy слушает `:80`. До сертификата это обычно **308** на https; для «Caddy жив» годятся 200, 301, 302, 307, 308. Workflow повторяет оба около трёх минут: `up -d` возвращается раньше, чем процессы начинают слушать.

Не проверяем деплой через `https://rekeeper.ru` и не используем `curl -k`. Пока нет публичного A или сертификат ещё не выпущен, такой curl роняет выкладку, хотя приложение живо. `-k` принимает любой сертификат и не доказывает Let's Encrypt.

Когда A смотрят на VPS:

```bash
curl -fsS https://rekeeper.ru/api/v1/health
```

`.env` в git нет: `reset --hard` его не трогает, `git clean` деплой не делает. Репозиторий публичный — для `git fetch` хватает `origin` = `https://github.com/ArturKolozyan/hackathon.git`.

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

### Серверный `.env` (HTTPS)

Файл деплой не перезаписывает. На VPS, до или сразу после мержа:

```
COOKIE_SECURE=true
CORS_ORIGINS=https://rekeeper.ru,https://www.rekeeper.ru,http://localhost:5173
```

Если править после уже идущих контейнеров: `docker compose up -d api` (workflow сам делает `up`, если `.env` готов до него).

Страница и `/api` на одном origin, nginx проксирует `/api`. Браузер для UI CORS не спрашивает. `CORS_ORIGINS` нужен для Vite `:5173` и прямого захода на API. Кука `SameSite=Lax`. `COOKIE_SECURE=true` — только HTTPS. Пока `false`, логин по https тоже работает, но браузер отправит куку и на первый http-запрос до редиректа Caddy. С `true` вход через голый http://127.0.0.1:8080 куку не сохранит — так и задумано.

`Domain` у куки нет: сессия на `rekeeper.ru` не общая с `www`. Оба хоста отдают одно приложение.

Локальный `.env.example` оставляет `COOKIE_SECURE=false`.

### Первый раз

Workflow каталог и `.env` не создаёт. Docker Compose на сервере уже есть. На хосте нужен `curl`. `WEB_PORT` оставить `8080` (это loopback).

```bash
git clone https://github.com/ArturKolozyan/hackathon.git /opt/invoice-keeper
cd /opt/invoice-keeper
cp .env.example .env
# на VPS: COOKIE_SECURE=true и CORS с https://rekeeper.ru, https://www.rekeeper.ru
docker compose up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

### Ручной деплой

```bash
ssh root@217.144.184.232
cd /opt/invoice-keeper && git fetch origin main && git reset --hard origin/main && docker compose up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: rekeeper.ru' http://127.0.0.1/
```

### Что хрупко у Caddy на этом VPS

- Исходящий HTTPS до `acme-v02.api.letsencrypt.org` с Москвы у Aeza обычно есть. Если в `docker compose logs caddy` таймаут на этот хост — сеть, не Caddyfile. DNS-01 и API Beget сюда не тащим.
- Пока домен NXDOMAIN, Caddy повторяет выпуск (пауза растёт, потолок — дни). После починки DNS подождать следующую попытку. Том `caddy_data` не пересоздавать: вместе с ним пропадёт аккаунт ACME, и неудачные попытки начнутся заново.
- Образ зафиксирован на `2.11.7-alpine`, не `latest`. Docker Hub с Aeza иногда тупит на `pull` — повторить `up`, чужой mirror не прописан.
- В логе может быть предупреждение quic про размер UDP-буфера. Это HTTP/3. Сайт по 443/tcp от него не зависит, sysctl не трогаем.
- HSTS не включён: если сертификат ещё красный, браузер не залипнет на https.
- Старый адрес `http://217.144.184.232:8080` снаружи больше не откроется.

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 плохо, IPv6 ок
- [x] Docker + Compose; снаружи 80/443 (Caddy), не публичный 8080
- [ ] Публичный ключ в `authorized_keys` и GitHub Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, опционально `DEPLOY_PORT`
- [ ] Публичный DNS: A `@` и `www` → `217.144.184.232`. На 2026-10-23 ещё NXDOMAIN. AAAA пустой или наш IPv6
- [ ] В серверном `.env`: `COOKIE_SECURE=true`, `CORS_ORIGINS` с `https://rekeeper.ru` и `https://www.rekeeper.ru`
- [ ] Деплой: health `http://127.0.0.1:8080/api/v1/health` и Caddy отвечает на `:80`
- [ ] `curl -fsS https://rekeeper.ru/api/v1/health` после появления A
- [ ] BotFather → токен + chat_id; `getMe` с VPS по IPv6

Следующий шаг: делегировать `rekeeper.ru` так, чтобы публичный A смотрел на VPS, и выставить `COOKIE_SECURE=true` в `/opt/invoice-keeper/.env` до мержа.
