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
| IP | `217.144.184.232` (IPv6 `2a14:a084:12e3::2`) |
| SSH | `ssh root@217.144.184.232` / `root` / `M0keAeffF751` |
| ОС | Ubuntu 26.04 |
| План | MSKs-2 · 2 CPU · 4 GB · 60 GB NVMe |
| Страна | **Москва, РФ** (Aeza) |
| Домен | `rekeeper.ru` (Beget). Канонический адрес — https://rekeeper.ru |
| Путь | `/opt/invoice-keeper` |
| Публичные порты | **80** и **443** (Caddy). `443/udp` — HTTP/3 |
| Авария | nginx только на `127.0.0.1:8080`. В интернет 8080 не открыт |

## Домен и HTTPS

Caddy (`caddy:2.11.7-alpine`) сам берёт сертификат Let's Encrypt и проксирует `rekeeper.ru` на сервис `web:80` в сети compose. Certbot не используем. Сертификаты и аккаунт ACME лежат в томе `caddy_data`. `docker compose down -v` их сотрёт, следующий запуск снова упрётся в лимит Let's Encrypt.

`www.rekeeper.ru` не отдаёт приложение: и HTTP, и HTTPS отвечают **301** на `https://rekeeper.ru` с тем же путём и query. Кука без `Domain`, поэтому сессия apex и www всё равно не общая — второй хост только редирект.

На 2026-10-23 публичные A `@` и `www` уже `217.144.184.232`. AAAA нет — для выпуска так и нужно. Чужой AAAA ломает ACME: Let's Encrypt ходит и по IPv6.

```bash
dig +short rekeeper.ru A
dig +short www.rekeeper.ru A
dig +short rekeeper.ru AAAA
```

- A `@` и `www` → `217.144.184.232`
- AAAA нет, **или** оба AAAA равны `2a14:a084:12e3::2`
- PTR `hack-user-jiqud9.ptr.network` не URL
- На хосте ufw выключен, политика INPUT — accept. Отдельного фаервола в ОС нет. Если в панели Aeza появится фильтр — пустить 80/tcp и 443/tcp

Caddy сжимает ответ (`gzip` и `zstd`). Nginx свой gzip не включает, иначе до zstd дело не доходит. Заголовки ответа с apex: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`. HSTS нет: если первый сертификат не выпустится, браузер не залипнет на https.

## Как открывать

| | |
|--|--|
| Сайт | https://rekeeper.ru |
| www | 301 на https://rekeeper.ru |
| На самом VPS | http://127.0.0.1:8080 — только loopback |
| PTR | не URL |

Аварийный вход, если Caddy или сертификат лежат:

```bash
ssh -L 8080:127.0.0.1:8080 root@217.144.184.232
```

Дальше в браузере http://127.0.0.1:8080. При `COOKIE_SECURE=true` браузер по этому HTTP сессию не сохранит: туннель годится, чтобы увидеть health и страницу входа. Логин в браузере — через https://rekeeper.ru. Если https мёртв и зайти надо именно так: на сервере временно `COOKIE_SECURE=false`, пересоздать `api`, зайти, вернуть `true` и снова пересоздать `api`.

Локально панель: http://localhost:8080, без Caddy. Команда в [README](../README.md). Полный `docker compose up` на ноутбуке полезет в Let's Encrypt за `rekeeper.ru` и может на час забить лимит неудачных попыток (5 на имя в час) перед первым выпуском на VPS.

## Порты

| Куда | Кто |
|------|-----|
| 80, 443/tcp, 443/udp | Caddy → `web:80` |
| 127.0.0.1:8080 | nginx. Авария и health деплоя |
| 127.0.0.1:8000 | API мимо nginx |
| 127.0.0.1:5432 | Postgres. Worker в сети хоста подключается сюда |

Раньше 5432, 8000 и 8080 слушали `0.0.0.0` и `[::]`. Снаружи это лишнее: Postgres и API были доступны из интернета. Проверки внутри контейнеров ходят сами в себя (`pg_isready`, API на `127.0.0.1:8000`) и от bind хоста не зависят.

На VPS не задавать `CADDY_HTTP_PORT` / `CADDY_HTTPS_PORT`. Иначе ACME стучится на 80, а Caddy слушает другой порт. Не задавать `COMPOSE_FILE`: деплой и так передаёт оба файла флагами `-f`. Если переменная всё же стоит, ручной `docker compose up` без флагов возьмёт её вместо обычного набора и может поднять стек без Caddy или без worker.

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут. С хоста это проверено.
- IPv6 → API отвечает (`curl -6` на `https://api.telegram.org` даёт ответ). Клиент в worker сажает сокет на `::`, когда `TELEGRAM_FORCE_IPV6=true`.
- Транспорт — long polling, не webhook. Токен и chat id только в `.env` на сервере.
- У bridge Docker на этом хосте нет маршрута IPv6 в интернет (`docker info` без IPv6). Worker поэтому в `network_mode: host` ([compose.telegram-host.yml](../compose.telegram-host.yml)): у него тот же IPv6, что у VPS (`2a14:a084:12e3::2`).
- `api`, `web` и `caddy` остаются в bridge. Caddy резолвит имя `web`. Им IPv6 не нужен.
- Postgres для worker — `127.0.0.1:5432`, не имя `db` (в сети хоста его нет). На VPS включён docker-proxy, и worker уже так ходит. Публикация порта только на `127.0.0.1` этот путь не меняет: proxy слушает loopback, контейнер в host network — тот же loopback. В URL именно `127.0.0.1`, не `localhost`: `localhost` может уехать на `::1`, а порт на `[::1]` не публикуется.

## Деплой

Push в `main` и ручной `workflow_dispatch` → [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) → SSH:

```bash
cd /opt/invoice-keeper
git fetch origin main
git reset --hard origin/main
docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: rekeeper.ru' http://127.0.0.1/
```

Оба `-f` прописаны в workflow. `COMPOSE_FILE` в серверном `.env` для этого не используется: файл деплой не меняет, забытая строка оставила бы worker в bridge, health по HTTP остался бы зелёным, Telegram — нет.

Workflow около трёх минут ждёт три условия:

1. `http://127.0.0.1:8080/api/v1/health` — тело непустое (nginx и API).
2. Caddy на `:80` с `Host: rekeeper.ru` — код 200, 301, 302, 307 или 308. До сертификата это обычно **308** на https.
3. Контейнер `worker` в статусе `running` и `NetworkMode=host`.

`https://rekeeper.ru` и `curl -k` в эту петлю не входят. Пока сертификат не выпущен, такой curl роняет выкладку, хотя приложение живо. `-k` принимает любой сертификат и не доказывает Let's Encrypt.

Когда A смотрит на VPS и выпуск прошёл:

```bash
curl -fsS https://rekeeper.ru/api/v1/health
curl -sI https://www.rekeeper.ru/api/v1/health
```

Второй ответ — `301` и `Location: https://rekeeper.ru/api/v1/health`.

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

### Серверный `.env`

Файл деплой не перезаписывает. До мержа, в `/opt/invoice-keeper/.env`, заменить или добавить ровно эти строки:

```
COOKIE_SECURE=true
CORS_ORIGINS=https://rekeeper.ru
APP_PUBLIC_URL=https://rekeeper.ru
```

Остальное не трогать ради этого куска: `WEB_PORT=8080`, `TELEGRAM_FORCE_IPV6=true`, токен бота как был. `CADDY_HTTP_PORT`, `CADDY_HTTPS_PORT`, `COMPOSE_FILE` не задавать.

`COOKIE_SECURE=true` API читает при старте. Если поправить `.env` после того, как workflow уже пересоздал контейнеры, нужен ещё один прогон:

```bash
docker compose -f docker-compose.yml -f compose.telegram-host.yml up -d api worker
```

Порядок без второго захода: сначала эти три строки, потом мерж.

Страница и `/api` на одном origin, nginx проксирует `/api` и передаёт `X-Forwarded-Proto` от Caddy. Браузер для UI CORS не спрашивает. `CORS_ORIGINS` — для прямого вызова API. `www` в список не входит: браузер на www не остаётся. Кука `SameSite=Lax`, `Secure` по флагу.

Локальный `.env.example` оставляет `COOKIE_SECURE=false`.

### Первый раз

Workflow каталог и `.env` не создаёт. Docker Compose на сервере уже есть. На хосте нужен `curl`.

```bash
git clone https://github.com/ArturKolozyan/hackathon.git /opt/invoice-keeper
cd /opt/invoice-keeper
cp .env.example .env
# затем три строки прода из раздела выше
docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
```

### Ручной деплой

```bash
ssh root@217.144.184.232
cd /opt/invoice-keeper && git fetch origin main && git reset --hard origin/main && docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: rekeeper.ru' http://127.0.0.1/
docker inspect -f '{{.HostConfig.NetworkMode}}' "$(docker compose -f docker-compose.yml -f compose.telegram-host.yml ps -q worker)"
```

Последняя строка должна напечатать `host`.

### Что хрупко у Caddy на этом VPS

- На 2026-10-23 порты 80 и 443 на хосте свободны, UDP 443 тоже. Если к мержу их займут, контейнер `caddy` не встанет, а 8080 уже только loopback: публичный сайт ляжет, туннель на 8080 останется. Перед мержем: `ss -ltnp | grep -E ':80|:443'`.
- Исходящий HTTPS до `acme-v02.api.letsencrypt.org` с Москвы у Aeza обычно есть. Таймаут в `docker compose logs caddy` на этот хост — сеть, не Caddyfile. DNS-01 и API Beget сюда не тащим.
- Пока выпуск не прошёл, Caddy повторяет его (пауза растёт). Том `caddy_data` не пересоздавать.
- Образ зафиксирован на `2.11.7-alpine`, не `latest`. Docker Hub с Aeza иногда тупит на `pull` — повторить workflow, чужой mirror не прописан.
- Предупреждение quic про размер UDP-буфера — это HTTP/3. Сайт по 443/tcp от него не зависит.
- Откат на коммит без Caddy: тот же `up` с `--remove-orphans`, иначе старый контейнер `caddy` продолжит держать 80/443. Том `caddy_data` при откате не удалять.

```bash
docker compose -f docker-compose.yml -f compose.telegram-host.yml up --build -d --remove-orphans
```

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 до Telegram таймаут, IPv6 отвечает; worker уже в сети host
- [x] Docker + Compose; ufw выключен; 80/443 на хосте свободны (снимок 2026-10-23)
- [x] DNS: A `@` и `www` → `217.144.184.232`, AAAA пустой
- [ ] Публичный ключ в `authorized_keys` и GitHub Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, опционально `DEPLOY_PORT`
- [ ] В серверном `.env` до мержа: `COOKIE_SECURE=true`, `CORS_ORIGINS=https://rekeeper.ru`, `APP_PUBLIC_URL=https://rekeeper.ru`
- [ ] Деплой: health `http://127.0.0.1:8080/api/v1/health`, Caddy на `:80` с `Host: rekeeper.ru`, worker `NetworkMode=host`
- [ ] `curl -fsS https://rekeeper.ru/api/v1/health` и 301 с `https://www.rekeeper.ru` на apex
- [ ] Снаружи 5432 и 8000 больше не открываются
- [ ] В логе worker нет таймаута IPv4 до `api.telegram.org`
- [ ] BotFather → токен + chat_id, если ещё не стоят в `.env`

Следующий шаг: три строки в `/opt/invoice-keeper/.env`, ещё раз `ss` на 80/443, мерж. После зелёного Actions — `curl` на https и заголовки.
