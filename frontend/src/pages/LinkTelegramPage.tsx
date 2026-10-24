import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type TelegramLink } from "../api";
import { useAuth } from "../auth";

export function LinkTelegramPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function openLink() {
    setBusy(true);
    setError(null);
    try {
      const body = await api<TelegramLink>("/api/v1/me/telegram/link", { method: "POST" });
      setLink(body.url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ссылку получить не удалось");
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/me/telegram/skip", { method: "POST" });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось пропустить");
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <section className="panel login-form">
        <h1>Привяжите Telegram</h1>
        <p className="desc">Личные напоминания и кнопка «Оплачено» заработают после привязки. Это можно сделать позже в разделе «Уведомления».</p>
        {link && (
          <p>
            <a href={link} target="_blank" rel="noreferrer">
              Открыть бота
            </a>
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row-actions">
          <button type="button" className="primary" disabled={busy} onClick={() => void openLink()}>
            {busy ? "…" : "Получить ссылку"}
          </button>
          <button type="button" className="ghost" disabled={busy} onClick={() => void skip()}>
            Пропустить
          </button>
        </div>
      </section>
    </div>
  );
}
