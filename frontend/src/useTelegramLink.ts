import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type TelegramLink, type TelegramSelf } from "./api";

/** Personal Telegram binding: get a deep link, then watch /me/telegram until the bot confirms it. */
export function useTelegramLink(onLinked: () => void) {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const linked = useRef(onLinked);
  linked.current = onLinked;

  useEffect(() => {
    if (!url) return;
    const timer = window.setInterval(() => {
      api<TelegramSelf>("/api/v1/me/telegram")
        .then((self) => {
          if (!self.linked) return;
          setUrl(null);
          linked.current();
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [url]);

  const request = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setUrl((await api<TelegramLink>("/api/v1/me/telegram/link", { method: "POST" })).url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ссылку получить не удалось");
    } finally {
      setBusy(false);
    }
  }, []);

  return { url, busy, error, request };
}
