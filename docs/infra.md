# Infra — сервер команды

[AGENTS.md](../AGENTS.md) · [product](product.md)

Хакатон: секреты здесь можно использовать как есть. VPS выдан организаторами — **баланс/продление не наша задача**.

## Каталог infra/

`.env` (в git нет) и `.env.example` — в корне репозитория. В `infra/`: `docker-compose.yml`, `caddy/` (`Caddyfile` и `entrypoint.sh`), `ops/` (бэкап, деплой, смоук, отчёт CI). Бэкапы — в корневом `backups/` (в git нет), compose монтирует `../backups`. Все команды из корня: `docker compose --env-file .env -f infra/docker-compose.yml …`; ниже для краткости `docker compose` в тексте означает именно это. Имя проекта `invoice-keeper` задано в compose-файле, тома и сеть те же, что до переезда.

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
| Авария | Caddy на `HTTP_PORT` (прод: 80). Панель снаружи — https://rekeeper.ru |

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
| На самом VPS | http://127.0.0.1/healthz при `HTTP_PORT=80` |
| PTR | не URL |

Аварийный вход, если Caddy или сертификат лежат:

```bash
ssh -L 8080:127.0.0.1:80 root@217.144.184.232
```

Дальше в браузере http://127.0.0.1:8080. При `COOKIE_SECURE=true` браузер по этому HTTP сессию не сохранит: туннель годится, чтобы увидеть health и страницу входа. Логин в браузере — через https://rekeeper.ru. Если https мёртв и зайти надо именно так: на сервере временно `COOKIE_SECURE=false`, пересоздать `api`, зайти, вернуть `true` и снова пересоздать `api`.

Локально панель: http://localhost:8080. `DOMAIN` пустой — Caddy отдаёт HTTP и в Let's Encrypt не ходит. Команда одна, из корня: `docker compose --env-file .env -f infra/docker-compose.yml up --build -d`, см. [README](../README.md). На ноутбуке не задавайте `DOMAIN=rekeeper.ru`: выпуск сертификата с чужой машины бьёт лимит Let's Encrypt.

## Порты

| Куда | Кто |
|------|-----|
| 80, 443/tcp, 443/udp | Caddy. На проде `HTTP_PORT=80`, `HTTPS_PORT=443`. Локально по умолчанию 8080 и 8443 |
| `HTTP_PORT` на хосте | единственный вход в панель. `web` наружу не публикуется |
| 127.0.0.1:8000 | API мимо Caddy (`API_PORT`) |
| 127.0.0.1:5432 | Postgres |

`web` больше не слушает 8080 сам. Аварийный туннель на проде: `ssh -L 8080:127.0.0.1:80`, затем http://127.0.0.1:8080. Health Caddy — `http://127.0.0.1/healthz` при `HTTP_PORT=80`.

Не задавать `COMPOSE_FILE`. Раньше он подключал `compose.telegram-host.yml`; файла больше нет, забытая строка ломает `docker compose up`. Не задавать старые `CADDY_HTTP_PORT` / `CADDY_HTTPS_PORT` / `WEB_PORT`: порты теперь `HTTP_PORT` и `HTTPS_PORT`.

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут. С хоста это проверено.
- IPv6 → API отвечает (`curl -6` на `https://api.telegram.org`).
- Транспорт — long polling в контейнере `bot`, не webhook и не сеть хоста. `api` и `worker` в Telegram не ходят: worker кладёт карточки в outbox, бот забирает. Постоянная ошибка отправки (бот заблокирован или выгнан, чата нет) закрывает карточку сразу, временная повторяется до 30 попыток и суток. Группа стала супергруппой — бот переносит id чата и шлёт ещё раз. Новая карточка периода снимает кнопку «Оплачено» со старой в том же чате.
- Чат отдела и личный Telegram привязываются из панели. `TELEGRAM_CHAT_ID` — запасной, только если отдел один. Ссылка привязки из панели живёт 15 минут, из письма — 3 дня.
- Сеть compose по умолчанию без IPv6 (`ENABLE_IPV6=false`), чтобы машины без IPv6 поднимались. На этом VPS в `.env`: `ENABLE_IPV6=true` и `TELEGRAM_NETWORK=ipv6`. `TELEGRAM_FORCE_IPV6=true` остаётся устаревшим алиасом, если сеть не задана.
- Отдельного `compose.telegram-host.yml` нет. Если bridge IPv6 не выходит в интернет, запасной путь — `TELEGRAM_PROXY`, не `network_mode: host`.
- Бот ходит в Postgres по имени `db`, как остальные сервисы. `depends_on` на бота и ассистента нет.

## Деплой

Push в `main`, pull request и ручной `workflow_dispatch` → [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

Три job по цепочке: `verify` → `deploy` → `healthcheck`. Первая упавшая проверка останавливает весь workflow. Новый запуск на той же ветке отменяет предыдущий. `deploy` только для push в `main` или ручного запуска с `main`. Pull request гоняет только `verify`.

`verify`, шаги по порядку:

| Шаг | Что |
|-----|-----|
| backup selftest | `sh infra/ops/backup/selftest.sh`: полночь МСК и ротация 7 файлов, без живой базы |
| pytest | Python 3.12, `pytest -x -ra --tb=short` в `backend/`. Postgres 16 — service GitHub Actions, `127.0.0.1:5433` (5432 занимает compose в smoke), пользователь `invoice` / `change-me`. Тесты сами создают базу `invoice_keeper_test` |
| web | Node 22, `npm ci`, `tsc --noEmit`, `vite build` в `frontend/` — три отдельных шага |
| smoke | `bash infra/ops/smoke.sh`: чистый `.env.example`, `docker compose up --build -d`, вход владельца, эндпоинты кейса, рестарт, остановленный `bot`, ассистент выключен без ключей и недоступен после `stop assistant` |

`deploy` — `ssh` с проверкой отпечатка хоста, на сервере выполняется [`infra/ops/deploy-remote.sh`](../infra/ops/deploy-remote.sh). `healthcheck` после деплоя ждёт ответа `https://rekeeper.ru/api/v1/health` до двух минут.

Упал шаг — в Summary запуска один блок от [`infra/ops/ci/report.sh`](../infra/ops/ci/report.sh): какой шаг, ключевые строки его лога (для pytest — секция FAILURES и итог), для smoke и deploy — `docker compose ps` и по 100 строк логов каждого сервиса, для healthcheck — последний HTTP-код и тело. Его и копировать. Полные логи шагов — артефакт `verify-logs` / `deploy-logs`.

Логи контейнеров: одна строка на запись `время уровень логгер текст`, traceback ниже. Уровень — `LOG_LEVEL` в `.env`, по умолчанию `INFO`. Необработанная ошибка запроса пишется uvicorn с traceback.

Деплой на сервере делает ровно то, что README: `git pull --ff-only origin main` и `docker compose --env-file .env -f infra/docker-compose.yml up --build -d` из корня.

SSH:

```bash
cd /opt/invoice-keeper
git pull --ff-only origin main
docker compose --env-file .env -f infra/docker-compose.yml up --build -d
curl -fsS http://127.0.0.1/healthz
curl -fsS https://rekeeper.ru/api/v1/health
```

`COMPOSE_FILE` в серверном `.env` надо удалить. Иначе compose подхватит исчезнувший override.

Health-wait читает `HTTP_PORT` из серверного `.env` (на проде 80). Ждёт `http://127.0.0.1:${HTTP_PORT}/healthz`. Если `DOMAIN` пустой — ещё и `/api/v1/health`. Если домен задан, https проверяется, но первый выпуск сертификата эту проверку не роняет. Контейнер `backup` по-прежнему поднимается вместе со стеком.

Когда A смотрит на VPS и выпуск прошёл:

```bash
curl -fsS https://rekeeper.ru/api/v1/health
curl -sI https://www.rekeeper.ru/api/v1/health
```

Второй ответ — `301` и `Location: https://rekeeper.ru/api/v1/health`.

`.env` в git нет: `git pull --ff-only` его не трогает, `git clean` деплой не делает. Репозиторий публичный — для `git fetch` хватает `origin` = `https://github.com/ArturKolozyan/hackathon.git`.

Actions ходит **ключом**, не паролем из таблицы SSH.

### GitHub Secrets

В репозиторий значения не коммитить. Пароль root сюда не класть.

| Secret | Что |
|--------|-----|
| `DEPLOY_HOST` | `217.144.184.232` |
| `DEPLOY_USER` | `root`. Владеет `/opt/invoice-keeper` и может `docker` |
| `DEPLOY_SSH_KEY` | приватный ключ целиком (PEM, с `BEGIN`/`END`), без passphrase. Публичная часть — в `/root/.ssh/authorized_keys` |
| `DEPLOY_PORT` | необязательно. Пусто = 22 |

Отпечаток для деплоя — **ECDSA** `SHA256:E+eFNJNFwH/+68XXrzlY+Gtpfs/5eRKrwHFmTWL+s3c`. Он зашит в workflow. Workflow берёт ключ хоста через `ssh-keyscan -t ecdsa` и до подключения сверяет его отпечаток с этим. ED25519 `SHA256:LpmjSctDQ1eIK1qjX8VOZKRIpLpVs6k1bh6BXzPBAfg`. RSA `SHA256:liIVVkDgQWnXMutSjzvkJLfc2YL77kdOVtkF0pe6cqY`. Переустановка VPS — снять отпечатки заново, иначе деплой отвергнет хост.

### Серверный `.env`

Файл деплой не перезаписывает. До мержа, в `/opt/invoice-keeper/.env`, заменить или добавить ровно эти строки:

```
COOKIE_SECURE=true
CORS_ORIGINS=https://rekeeper.ru
APP_PUBLIC_URL=https://rekeeper.ru
```

К этим строкам один раз добавить переход на общий compose. Удалить `COMPOSE_FILE`, `WEB_PORT`, `CADDY_HTTP_PORT`, `CADDY_HTTPS_PORT`. Выставить:

```
DOMAIN=rekeeper.ru
HTTP_PORT=80
HTTPS_PORT=443
ENABLE_IPV6=true
TELEGRAM_NETWORK=ipv6
```

Токен бота оставить. Если ключ GigaChat уже есть — `COMPOSE_PROFILES=assistant`, иначе профиль пустой. `SEED_DEMO=false`, пока в базе есть отделы. Том `caddy_data` не удалять.

`COOKIE_SECURE=true` API читает при старте. Если поправить `.env` после того, как workflow уже пересоздал контейнеры, нужен ещё один прогон:

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d api worker bot
```

Порядок без второго захода: сначала эти три строки, потом мерж.

Страница и `/api` на одном origin, nginx проксирует `/api` и передаёт `X-Forwarded-Proto` от Caddy. Имя `api` резолвится при запросе (Docker DNS `127.0.0.11`, кэш 10 с, только IPv4). Иначе после `docker compose up -d --force-recreate api` web держит старый IP и `/api/*` отвечает 502, пока не перезапустишь web. Браузер для UI CORS не спрашивает. `CORS_ORIGINS` — для прямого вызова API. `www` в список не входит: браузер на www не остаётся. Кука `SameSite=Lax`, `Secure` по флагу.

Локальный `.env.example` оставляет `COOKIE_SECURE=false`.

### Первый раз

Workflow каталог и `.env` не создаёт. Docker Compose на сервере уже есть. На хосте нужен `curl`.

```bash
git clone https://github.com/ArturKolozyan/hackathon.git /opt/invoice-keeper
cd /opt/invoice-keeper
cp .env.example .env
# затем три строки прода из раздела выше
docker compose --env-file .env -f infra/docker-compose.yml up --build -d
curl -fsS http://127.0.0.1/healthz
```

### Ручной деплой

```bash
ssh root@217.144.184.232
cd /opt/invoice-keeper && git pull --ff-only origin main && docker compose --env-file .env -f infra/docker-compose.yml up --build -d
curl -fsS http://127.0.0.1/healthz
curl -fsS https://rekeeper.ru/api/v1/health
docker compose --env-file .env -f infra/docker-compose.yml ps
```

`bot` в bridge, не в `host`. `backup` — `running`, в `backups/` лежит дамп. Если 80/443 уже держит сервис `caddy` этого compose, его не останавливать. Чужой процесс на этих портах — остановить до `up`.

### Что хрупко у Caddy на этом VPS

- На 2026-10-23 порты 80 и 443 на хосте свободны, UDP 443 тоже. Если к мержу их займут, контейнер `caddy` не встанет, а 8080 уже только loopback: публичный сайт ляжет, туннель на 8080 останется. Перед мержем: `ss -ltnp | grep -E ':80|:443'`.
- Исходящий HTTPS до `acme-v02.api.letsencrypt.org` с Москвы у Aeza обычно есть. Таймаут в `docker compose logs caddy` на этот хост — сеть, не Caddyfile. DNS-01 и API Beget сюда не тащим.
- Пока выпуск не прошёл, Caddy повторяет его (пауза растёт). Том `caddy_data` не пересоздавать.
- Образ зафиксирован на `2.11.7-alpine`, не `latest`. Docker Hub с Aeza иногда тупит на `pull` — повторить workflow, чужой mirror не прописан.
- Предупреждение quic про размер UDP-буфера — это HTTP/3. Сайт по 443/tcp от него не зависит.
- Откат на коммит без Caddy: тот же `up` с `--remove-orphans`, иначе старый контейнер `caddy` продолжит держать 80/443. Том `caddy_data` при откате не удалять.

```bash
docker compose --env-file .env -f infra/docker-compose.yml up --build -d --remove-orphans
```

## Бэкапы Postgres

Отдельный сервис `backup` в [infra/docker-compose.yml](../infra/docker-compose.yml), не systemd-таймер на хосте.

Деплой и так делает `docker compose up`. Сервис поднимается и откатывается вместе с репозиторием. Unit на хосте пришлось бы ещё копировать и `enable` в том же SSH, и при откате коммита таймер остался бы старым. `pg_dump` берётся из того же образа `postgres:16-alpine`, что и сервер: клиент на хост ставить не нужно, версии не разъедутся. В `postgres:16-alpine` нет cron и tzdata, пакеты при старте не ставим (зеркала с Москвы лишняя точка отказа). Цикл в `ops/backup/loop.sh` спит до полуночи. Москва — UTC+3 круглый год, без летнего времени, поэтому полночь считается от `date -u`, а не от часового пояса контейнера.

Дамп — custom-формат (`pg_dump -Fc`, сжатие 6). Это не `.sql.gz`: gzip его не открывает, восстановление — `pg_restore`. Пароль только в `PGPASSWORD` внутри контейнера, в командную строку не попадает. Каталог на хосте — `./backups` от корня репозитория. На VPS это `/opt/invoice-keeper/backups`. `git reset --hard` его не трогает, `git clean` деплой не делает. Права каталога `700`. Контейнер идёт от root: у образа Postgres пользователь `postgres`, ему хостовый каталог не записать. Сервер базы этот контейнер не запускает. В git дампы не коммитить.

Расписание: каждый день в 00:00 по Москве, хранятся **7 последних файлов**, не «7 календарных дней, если за день их несколько». Старые удаляются только после успешного нового дампа. Неудачный `pg_dump` оставляет предыдущие файлы и повторяется через минуту. Если контейнер проспал полночь, при старте снимает один дамп за текущие сутки, когда файла за эту дату ещё нет. Имя: `invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump`, время в имени — московское.

`backup` в bridge и ходит в `db:5432`. `docker compose down` останавливает и бэкап. Пока стек поднят, цикл жив (`restart: unless-stopped`). В список контейнеров кейса он не входит: это служебный дамп рядом с продуктом.

`loop.sh` читается при старте процесса. `docker compose up` пересоздаёт `backup`, если изменился compose. Правка только скрипта подхватывается после `docker compose up -d --force-recreate --no-deps backup`. `backup.sh` запускается заново на каждый дамп.

Дампы лежат на том же диске, что Postgres. Это защита от плохого деплоя и случайного затирания данных, не от смерти диска.

Проверка после деплоя:

```bash
cd /opt/invoice-keeper
docker compose --env-file .env -f infra/docker-compose.yml ps backup
docker compose --env-file .env -f infra/docker-compose.yml logs --tail=20 backup
ls -l backups
```

В логе есть `backup wrote` (первый запуск за сутки) или `next backup at 00:00 Europe/Moscow`. Файл в `backups/` непустой.

### Восстановление

Скрипт [infra/ops/backup/restore.sh](../infra/ops/backup/restore.sh) останавливает `api`, `worker`, `bot` и `backup` (чтобы не писали в ту же базу), сессии к базе обрывает, `pg_restore --clean --if-exists` прогоняет внутри контейнера `db`. Пока `api` стоит, распаковывает в том `receipts` архив `receipts-<тот же штамп>-*.tar.gz` из того же каталога (старое содержимое тома заменяется; архива нет — файлы остаются как есть). Затем снова запускает эти сервисы и ждёт `/healthz` на `HTTP_PORT` из `.env`. Postgres не останавливается. Без `--yes` скрипт ничего не делает.

```bash
cd /opt/invoice-keeper
infra/ops/backup/restore.sh --yes backups/invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump
```

Сегодняшний файл после восстановления не перезаписывается до следующей полуночи. Нужен новый снимок сразу — удалить `backups/invoice-keeper-<сегодня>T*.dump` и перезапустить `backup`:

```bash
docker compose --env-file .env -f infra/docker-compose.yml restart backup
```

### Файлы чеков

Чеки (PDF и фото) лежат в именованном томе `receipts`: `api` монтирует его в `/data/receipts` (`RECEIPTS_DIR`), `backup` — только на чтение в `/receipts`. Каждый дамп базы сопровождается архивом `backups/receipts-YYYYMMDDTHHMMSS-<pid>.tar.gz`, ротация та же — `BACKUP_KEEP` последних. Архив — полный снимок тома, поэтому на диске всегда 7 суточных полных архивов чеков (при `BACKUP_KEEP=7`): место считать как 7 × размер тома. Ошибка архива не отменяет дамп базы, в лог `backup` уходит строка `ERROR: receipts archive failed`. `restore.sh` возвращает чеки сам. Только файлы, без базы:

```sh
docker compose run --rm -v "$PWD/backups:/b:ro" --entrypoint sh api -c 'tar -xzf /b/receipts-YYYYMMDDTHHMMSS-<pid>.tar.gz -C /data/receipts'
```

Файлы, на которые не ссылается ни один период, и недописанные `*.part` старше часа `api` стирает при старте. Вручную: `docker compose exec api python -m app.receipts_sweep`.

Бэкапы лежат на том же диске, что и база. Копию `backups/` держать вне VPS: например, cron на другой машине раз в сутки после 00:30 по Москве делает `rsync -a --delete root@<vps>:/opt/invoice-keeper/backups/ /srv/rekeeper-backups/`.

Курсы для подсказки «≈ … ₽» под суммой в USD и EUR `api` берёт у ЦБ РФ (`www.cbr.ru/scripts/XML_daily.asp`, запасной `www.cbr-xml-daily.ru`), держит в памяти и обновляет раз в час. ЦБ недоступен — подсказки нет, остальное работает. В итоги курс не входит.

Лимит размера чека — `RECEIPT_MAX_MB` (по умолчанию 10). nginx в `web` пропускает тело до 12 МБ.

Сколько файлов держать — `BACKUP_KEEP` в `.env` (по умолчанию 7). Остальной `.env` ради бэкапа не трогать.

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 до Telegram таймаут, IPv6 отвечает. Бот в bridge, на этом VPS `ENABLE_IPV6=true` и `TELEGRAM_NETWORK=ipv6`
- [x] Docker + Compose; ufw выключен; 80/443 на хосте свободны (снимок 2026-10-23)
- [x] DNS: A `@` и `www` → `217.144.184.232`, AAAA пустой
- [ ] Публичный ключ в `authorized_keys` и GitHub Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, опционально `DEPLOY_PORT`
- [ ] В серверном `.env` до мержа: `COOKIE_SECURE=true`, `CORS_ORIGINS=https://rekeeper.ru`, `APP_PUBLIC_URL=https://rekeeper.ru`
- [ ] Деплой: `http://127.0.0.1/healthz` и `https://rekeeper.ru/api/v1/health`, бот не в host network, backup running и файл в `backups/`
- [ ] `curl -fsS https://rekeeper.ru/api/v1/health` и 301 с `https://www.rekeeper.ru` на apex
- [ ] Снаружи 5432 и 8000 больше не открываются
- [ ] В логе `bot` нет таймаута IPv4 до `api.telegram.org` и нет пути `api.telegram.org/bot<токен>/`
- [ ] `backup` running, в `/opt/invoice-keeper/backups` есть `invoice-keeper-*.dump`
- [ ] BotFather → токен + chat_id, если ещё не стоят в `.env`

Следующий шаг: в `/opt/invoice-keeper/.env` домен, порты 80/443, IPv6 и удаление `COMPOSE_FILE`; `ss` на 80/443 и остановить только чужой процесс, если порт занят не нашим `caddy`; мерж. После зелёного Actions — `curl` на https, лог `bot` без токена, файл в `backups/`.
