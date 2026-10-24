---
name: rekeeper
description: Инбокс обязательств команды. Тёмный кабинет, один оранжевый, очередь карточек.
colors:
  accent: "#FF6B1A"
  accent-hover-dark: "#FF8A47"
  accent-hover-light: "#D9560C"
  on-accent: "#0E0E0E"
  accent-ink-dark: "#FF6B1A"
  accent-ink-light: "#B44000"
  bg-dark: "#0E0E0E"
  surface-dark: "#1A1A1A"
  border-dark: "#2A2A2A"
  field-dark: "#121212"
  text-dark: "#FFFFFF"
  muted-dark: "#A3A3A3"
  bg-light: "#FAF6EC"
  surface-light: "#FFFFFF"
  border-light: "#E8E0CC"
  text-light: "#1F1B16"
  muted-light: "#6E665A"
  overdue: "#E5483D"
  overdue-ink-light: "#C5362C"
  soon: "#E0A100"
  soon-ink-light: "#8A5E00"
  paid: "#22A35A"
  paid-ink-light: "#157A42"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "clamp(2.4rem, 5vw, 3.3rem)"
    fontWeight: 800
    lineHeight: 1.12
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.85rem"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "0.08em"
rounded:
  card: "16px"
  control: "12px"
  field: "10px"
  pill: "4px"
spacing:
  grid: "8px"
  tight: "8px"
  card: "16px"
  section: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover-dark}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.accent-ink-dark}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "44px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "44px"
  card:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.card}"
    padding: "14px 16px"
  input:
    backgroundColor: "{colors.field-dark}"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
    height: "44px"
  pill-overdue:
    backgroundColor: "{colors.overdue}"
    textColor: "{colors.overdue}"
    rounded: "{rounded.pill}"
    padding: "3px 10px 3px 8px"
---

# Design System: rekeeper

Канон для людей — [docs/design.md](docs/design.md). Этот файл зеркалит уже принятую систему (решение Artur, 2026-10-23, контраст — 2026-10-24) в формате DESIGN.md. Нового визуального направления нет. Если значения расходятся, верны `docs/design.md` и `frontend/src/styles.css`.

## Overview

**Creative North Star: "Очередь на тёмном столе"**

Кабинет плотный: поверхности близко к фону, воздух даёт шаг 8px, не серая бумага и не тень. Один оранжевый отмечает действие и сумму, которая ждёт решения. Инбокс читается сверху вниз: просрочено, скоро, остальное.

Светлая тема — та же очередь на слоновой кости. Оранжевый не меняется. Дефолт тёмный, даже если у системы светлая схема. Переключатель в шапке, значение в `localStorage` (`rekeeper-theme`).

**Key Characteristics:**

- Один акцент `#FF6B1A` на обе темы
- Очередь карточек, не таблица платежей
- Мягкие пилюли статусов, без заливки кнопки
- Inter, wordmark rekeeper, знак команды мелко
- Без теней

## Colors

Палитра уже названа в docs/design.md. Здесь те же hex.

### Primary

- **Сигнальный оранжевый** (`colors.accent`): заливка кнопки primary, линейка под суммой в инбоксе и в итогах, активная навигация на 16% заливке. Не статус и не фон экрана. Текст на этой заливке — `colors.on-accent`.
- **Чернила акцента** (`colors.accent-ink-dark` / `colors.accent-ink-light`): оранжевый как текст и обводка. На тёмной совпадает с заливкой. На светлой темнее, заливка не меняется.

### Neutral

- **Ночной фон** (`colors.bg-dark`) и **ночная карточка** (`colors.surface-dark`): дефолтная тема. Граница — `colors.border-dark`. Поле формы чуть темнее карточки (`colors.field-dark`).
- **Слоновая кость** (`colors.bg-light`) и **белая карточка** (`colors.surface-light`): светлая тема. Граница — `colors.border-light`.
- Текст и приглушённый текст меняются с темой: белый / `#A3A3A3` ночью, `#1F1B16` / `#6E665A` днём.

### Named Rules

**The One Orange Rule.** Заливка `#FF6B1A` только у CTA и у линейки суммы. Статусы её не занимают. Второй заливочный оранжевый не добавляется.

**Contrast.** На заливке акцента текст тёмный: `--on-accent` `#0E0E0E`, обе темы, включая hover `#FF8A47` и `#D9560C`. Оранжевый текст и обводка — `--accent-ink`: `#FF6B1A` на тёмной, `#B44000` на светлой. Приглушённый текст светлой темы — `#6E665A`.

**The Soft Status Rule.** Оплачено `#22A35A`, скоро `#E0A100`, просрочено `#E5483D`. Пилюля — прямоугольник 4px, 16% канона, текст каноном на тёмной теме, без точки. На светлой текст темнее: `#157A42`, `#8A5E00`, `#C5362C`. «Впереди» — `--muted` на 16%, без четвёртого цвета.

## Typography

**Display Font:** Inter (system-ui, sans-serif)
**Body Font:** Inter (system-ui, sans-serif)

**Character:** Один гротеск на латиницу и кириллицу. Wordmark — Inter Black в SVG, не живой текст. Веса интерфейса 400–800. Не Manrope и не IBM Plex.

### Hierarchy

- **Display** (800, clamp 2.4–3.3rem, −0.04em): только обещание на экране входа.
- **Headline** (700, 1.85rem): заголовок экрана.
- **Title** (700, 1.05rem): имя периода, шаблона, человека.
- **Body** (400, 16px, 1.45): пояснения. Длинный текст держать около 68ch.
- **Label** (700, 0.75rem, трекинг 0.08em, верхний регистр): кикер экрана и подписи итогов.

Суммы — `tabular-nums`.

### Named Rules

**The Inter Rule.** Семейство зафиксировано. Детектор «overused font» на Inter — ложное срабатывание относительно этого брифа.

## Layout

Шапка фиксирована на всю ширину, под ней сетка: навигация 220px на высоту окна и рабочая область, скролл только у содержимого. «Выйти» внизу колонки. Контент до 1040px, календарь на всю рабочую ширину. Шаг 8. До 860px колонка прячется в панель. Ориентир телефона — 390px: имя в шапке прячется, горизонтального скролла нет, касание не ниже 40px. Шрифт интерфейса — `--font-sans` и шкала `--fs-*` в styles.css.

## Elevation & Depth

Тени не используются. Глубина — это смена поверхности (фон → карточка) и граница 1px. Всплывающий слой календаря, если он ещё есть в коде, не образец: правка даты живёт в карточке.

### Named Rules

**The Flat Rule.** Нет `box-shadow` у карточек, меню и тостов. Кольцо фокуса поля — обводка акцента, не тень-ореол как декорация.

## Shapes

Карточка и диалоговая поверхность — 16px. Кнопки — 12px. Поля — 10px. Пилюля статуса — 4px. Линейка суммы — 999px. Круглые только кнопка чата, микрофон и отправка. Углы не острые и не «пузыри» на весь экран.

## Components

### Buttons

- **Shape:** скругление 12px, высота не ниже 40px.
- **Primary:** заливка акцента, текст `#0E0E0E`. Hover — `#FF8A47` ночью и `#D9560C` днём, текст тот же.
- **Secondary:** прозрачный фон, обводка и текст `--accent-ink`. Пример — «Дата».
- **Ghost:** обводка границы, текст обычный. Отмена и тихие действия.

### Chips

- **Style:** текст, фон 16% статуса, радиус 4px, без точки и без обводки.
- **State:** цвет = смысл (оплачено, скоро, просрочено, нейтральное). Это не кнопка.

### Cards / Containers

- **Corner Style:** 16px.
- **Background:** surface текущей темы.
- **Shadow Strategy:** нет.
- **Border:** 1px, `--border`.
- **Internal Padding:** 14–16px.
- Сумма в инбоксе и в итогах с короткой оранжевой линейкой. В истории и у админа линейки нет.

### Inputs / Fields

- **Style:** фон `--field`, граница `--border`, радиус 10px.
- **Focus:** граница `--accent-ink`.
- **Error:** текст цветом чернил просрочки, жирный, с `role="alert"`.

### Navigation

Тихий текст `--muted`, иконка lucide, активный пункт — текст обычный на 16% акцента, радиус 10px. На узком экране колонка выезжает панелью. Wordmark слева в шапке, тема справа. «Выйти» внизу колонки. «404 mercy not found» — вес 800, мелко, opacity около 0.22: над «Выйти», на входе в подвале.

### Amount rule

Короткая линия 36×3px под числом, только там, где решение про деньги ещё впереди: инбокс и итоги.

## Do's and Don'ts

### Do:

- **Do** держать один `#FF6B1A`, тёмный дефолт и очередь просрочено → скоро → остальное.
- **Do** брать новые куски (скелет, пусто, ошибка, тост, подтверждение в карточке, сегмент) только из этих токенов.
- **Do** писать интерфейс по-русски и называть период так, как его видит человек.

### Don't:

- **Don't** менять hex, Inter, радиусы 16/12/10, пилюлю 4px, шаг 8 и запрет теней.
- **Don't** добавлять градиенты, второй акцент, бумажный фон, Manrope, cyan AEZA или заливные статус-кнопки.
- **Don't** превращать инбокс в таблицу и писать «Invoice Keeper» в UI.
- **Don't** возвращать белый текст на `#FF6B1A` и не красить заливку в `--accent-ink`.
