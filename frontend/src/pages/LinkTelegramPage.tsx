import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { HINTS } from "../hints";
import { useTelegramLink } from "../useTelegramLink";

export function LinkTelegramPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [skipError, setSkipError] = useState<string | null>(null);
  const [skipping, setSkipping] = useState(false);
  const binding = useTelegramLink(() => {
    void refresh().then(() => navigate("/", { replace: true }));
  });
  const busy = binding.busy || skipping;
  const error = binding.error ?? skipError;

  async function skip() {
    setSkipping(true);
    setSkipError(null);
    try {
      await api("/api/v1/me/telegram/skip", { method: "POST" });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setSkipError(err instanceof ApiError ? err.message : "Не получилось пропустить");
      setSkipping(false);
    }
  }

  return (
    <div className="login-page">
      <section className="panel login-form">
        <h1>Привяжите Telegram</h1>
        <p className="desc">
          Одна привязка на всё: «Оплачено» в чате отдела записывается на вас, личные напоминания приходят в Telegram.
          Можно сделать позже: Настройки → Уведомления.
        </p>
        {binding.url && (
          <p className="desc" role="status">
            Откройте бота и нажмите «Старт». Страница обновится сама, как только привязка пройдёт.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row-actions">
          {binding.url ? (
            <a className="primary" href={binding.url} target="_blank" rel="noreferrer">
              Открыть бота
            </a>
          ) : (
            <button type="button" className="primary" disabled={busy} data-hint={HINTS.tgGetLink} onClick={() => void binding.request()}>
              {binding.busy ? "Получаем ссылку…" : "Получить ссылку"}
            </button>
          )}
          <button type="button" className="ghost" disabled={busy} data-hint={HINTS.tgSkip} onClick={() => void skip()}>
            Пропустить
          </button>
        </div>
      </section>
    </div>
  );
}
