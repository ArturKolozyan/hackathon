# QA

[product](product.md) · [AGENTS.md](../AGENTS.md)

Чеклист must из брифа + should (кнопка TG, календарь, чек/ссылка, фильтры инбокса). Баги — таблицей ниже.

| ID | Что | Статус |
|----|-----|--------|
| N1 | Дедуп (период, событие, канал, получатель), повторный тик | pytest `test_dispatch_dedups_t3_and_overdue` |
| N2 | Напоминания T-7 и T-3, в день срока тишина, просрочка со следующего дня и ежедневно | pytest `test_events_split_reminder_and_overdue` |
| N3 | Личный скоуп: свои платежи или весь отдел; выключенный Telegram молчит и для ответственного | pytest `test_personal_scope_follows_responsibility_and_telegram_toggle` |
| N4 | Участник читает каналы команды, не меняет | pytest `test_member_reads_team_channels_but_cannot_change_them` |
| N5 | Подключение чата — одна сводка, без пачки карточек | pytest `test_connect_sends_summary_not_cards` |
| N6 | «Оплачено»: плательщик = нажавший и член команды | pytest `test_button_marks_paid_by_linked_user_and_keeps_note`, `test_unlinked_and_outsider_cannot_mark_paid` |
