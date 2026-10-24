"""Письма аккаунта. Напоминания о платежах живут отдельно и смотрят на SMTP_TO."""

import html
import logging

from app.integrations.email import public_url, send_auth_email

log = logging.getLogger("invoice_keeper.mail")

_TITLES = {
    "register": ("Код для регистрации", "Введите его в rekeeper. Код действует 15 минут."),
    "reset_password": ("Сброс пароля", "Если вы не запрашивали сброс, это письмо можно закрыть. Код действует 15 минут."),
    "change_email": ("Новая почта", "Подтвердите адрес. Код действует 15 минут."),
}


def send_code(*, email: str, purpose: str, code: str) -> str:
    title, intro = _TITLES.get(purpose, ("Код rekeeper", "Код действует 15 минут."))
    text, html_body = _letter(
        title,
        intro,
        f"Код: {code}",
        f'<div style="font-size:32px;font-weight:700;letter-spacing:0.28em;">{html.escape(code)}</div>',
    )
    delivery = send_auth_email(to=email, subject=f"{title} — rekeeper", text=text, html=html_body)
    if delivery == "log":
        log.warning("SMTP не настроен, dev-режим: код %s для %s (%s)", code, email, purpose)
    return delivery


def send_account_created(db, user) -> str:
    """Логин, ссылка на вход и ссылка привязки Telegram. Без SMTP запрос не падает."""
    from app.services.telegram_links import bot_username, deep_link, issue_token

    panel = public_url() or "http://localhost:8080"
    login = f"{panel}/login"
    lines = [
        f"Для вас создана учётная запись rekeeper.",
        f"Почта: {user.email}",
        f"Вход: {login}",
        "Пароль вам передаст администратор. При первом входе его нужно сменить.",
    ]
    html_bits = [
        f"<p>Почта: <b>{html.escape(user.email)}</b></p>",
        f'<p><a href="{html.escape(login, quote=True)}">Войти в rekeeper</a></p>',
        "<p>Пароль вам передаст администратор. При первом входе его нужно сменить.</p>",
    ]
    username = bot_username(db)
    if username:
        token = issue_token(db, purpose="user", user=user)
        link = deep_link(username, token.token, group=False)
        lines.append(f"Привязать Telegram: {link}")
        lines.append("Ссылка действует 15 минут. Позже её можно запросить ещё раз в разделе «Люди».")
        html_bits.append(f'<p><a href="{html.escape(link, quote=True)}">Привязать Telegram</a></p>')
    else:
        lines.append("Привязку Telegram можно сделать после входа: Уведомления → Привязать Telegram.")
    text, html_body = _letter(
        "Доступ в rekeeper",
        "Вас добавили в систему регулярных платежей.",
        "\n".join(lines),
        "".join(html_bits),
    )
    delivery = send_auth_email(to=user.email, subject="Доступ в rekeeper", text=text, html=html_body)
    if delivery == "log":
        log.warning("SMTP не настроен: учётка %s создана, письмо не отправлено", user.email)
    return delivery


def send_invite(*, email: str, team_name: str, role: str, url: str) -> str:
    role_ru = "администратором" if role == "admin" else "участником"
    title = f"Вас зовут в «{team_name}»"
    intro = f"Вы вступите {role_ru}. Ссылка одноразовая и живёт 7 дней."
    text_block = f"Открыть приглашение: {url}"
    button = (
        f'<a href="{html.escape(url, quote=True)}" '
        'style="display:inline-block;background:#FF6B1A;color:#ffffff;text-decoration:none;'
        'padding:12px 18px;border-radius:12px;font-weight:700;">Принять приглашение</a>'
    )
    text, html_body = _letter(title, intro, text_block, button)
    delivery = send_auth_email(to=email, subject=f"{title} — rekeeper", text=text, html=html_body)
    if delivery == "log":
        log.warning("SMTP не настроен, dev-режим: приглашение %s для %s", url, email)
    return delivery


def _letter(title: str, intro: str, text_block: str, html_block: str) -> tuple[str, str]:
    panel = public_url()
    lines = ["rekeeper", "", title, "", intro, "", text_block, "", "Если вы не запрашивали письмо, ничего делать не нужно."]
    if panel:
        lines.extend(["", panel])
    text = "\n".join(lines)
    foot = f'<p style="margin-top:24px;"><a href="{html.escape(panel, quote=True)}" style="color:#FF6B1A;">{html.escape(panel)}</a></p>' if panel else ""
    html_body = f"""<!doctype html>
<html lang="ru"><body style="margin:0;background:#0E0E0E;color:#ffffff;font-family:Inter,Arial,sans-serif;">
<div style="max-width:520px;margin:0 auto;padding:32px 20px;">
  <div style="font-weight:900;font-size:22px;letter-spacing:-0.04em;"><span style="color:#FF6B1A;">re</span>keeper</div>
  <h1 style="font-size:24px;font-weight:700;letter-spacing:-0.03em;margin:24px 0 8px;">{html.escape(title)}</h1>
  <p style="color:#A3A3A3;line-height:1.5;margin:0 0 20px;">{html.escape(intro)}</p>
  <div style="padding:18px;border:1px solid #2A2A2A;border-radius:16px;background:#1A1A1A;">{html_block}</div>
  <p style="color:#A3A3A3;font-size:13px;line-height:1.45;">Если вы не запрашивали это письмо, ничего делать не нужно.</p>
  {foot}
</div></body></html>"""
    return text, html_body
