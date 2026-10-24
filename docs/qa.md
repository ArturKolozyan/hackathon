# QA

[product](product.md) · [AGENTS.md](../AGENTS.md)

Чеклист must из брифа + should (кнопка TG, календарь, чек/ссылка, фильтры инбокса). Баги — таблицей ниже.

| ID | Что | Статус |
|----|-----|--------|
| N1 | Дедуп (период, событие, канал, получатель), повторный тик | pytest `test_dispatch_dedups_t3_and_overdue` |
| N2 | Напоминание T-3…день срока и просрочка со следующего дня | pytest `test_events_split_reminder_and_overdue` |
| N3 | Скоуп личных каналов; ответственному личка обязательна | pytest `test_scope_limits_mail_and_responsible_dm_is_mandatory` |
| N4 | Участник читает каналы команды, не меняет | pytest `test_member_reads_team_channels_but_cannot_change_them` |
| N5 | Подключение чата — одна сводка, без пачки карточек | pytest `test_connect_sends_summary_not_cards` |
| N6 | «Оплачено»: плательщик = нажавший и член команды | pytest `test_button_marks_paid_by_linked_user_and_keeps_note`, `test_unlinked_and_outsider_cannot_mark_paid` |
