# AGENTS.md — оркестратор

Перед работой: этот файл, затем нужный файл в [docs/](docs/README.md). Продукт и процессы — только в `docs/`.

## Кто есть кто

| Роль | Кто | Зона |
|------|-----|------|
| Капитан | Artur | Решения, push, защита |
| Хакатон | Grok Bot | Кейс, продукт, стек после «ок», код/промпты |
| Team Lead | Grok Bot | Организация команды (6 чел.) |
| Cursor-агенты | ПК Artur / друга | Код по ТЗ из docs |

## Источник правды

1. Локально: `C:\Users\artur\Projects\hackathon` — боты читают с диска.
2. GitHub: https://github.com/ArturKolozyan/hackathon — шаринг после push.
3. Ветка `main`. Файлы репо важнее памяти чата.

## Кейс

**Invoice Keeper (AEZA), Middle, 100 000 ₽** — детали в [docs/product.md](docs/product.md).

## Решения

1. Сначала продукт, потом техника.
2. Artur решает; агент — варианты + рекомендация.
3. Качество > хаки; секреты хакатона можно использовать как есть.
4. С Artur — по-русски, коротко; всегда следующий шаг и что нужно от него.

## Cursor-агенты

Читать `AGENTS.md` + [docs/product.md](docs/product.md). Не раздувать скоуп. Must из product; should — только если must зелёный. README, `.env.example`, OpenAPI + Swagger обязательны. Push — по слову Artur.

## Grok-боты

Хакатон = продукт/кейс. Team Lead = орг. Читать с ПК. Договорённости писать в этот файл и `docs/`, не только в чат.

## Структура

```
hackathon/
├── AGENTS.md
├── README.md
└── docs/
    ├── README.md
    ├── product.md
    ├── design.md
    ├── pitch.md
    └── qa.md
```

Код приложения появится рядом по мере разработки.

Актуально: 2026-10-23.