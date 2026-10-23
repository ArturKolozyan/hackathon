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
| Домен | нет |

## Telegram с этого VPS

- IPv4 → `api.telegram.org` — таймаут (блокировка).
- IPv6 → API отвечает. Worker должен ходить на Telegram по **IPv6** (или proxy вне РФ).

## Чеклист

- [x] SSH ок
- [x] Страна / TG: Москва; IPv4 плохо, IPv6 ок
- [ ] Docker + Compose; порты 22/80/443
- [ ] BotFather → токен + chat_id; `getMe` с VPS по IPv6
- [ ] Деплой веб+api+worker
- [ ] (опц.) домен + DNS
