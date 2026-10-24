import { useEffect, useState } from "react";

const CHANGED = "rekeeper:changed";

/** Данные поменялись не на этой странице (ассистент, другая вкладка): страницы перечитают своё. */
export function notifyChanged() {
  window.dispatchEvent(new Event(CHANGED));
}

/**
 * Счётчик свежести. Растёт, когда вкладка снова на экране или данные поменялись в другом месте.
 * Страница добавляет его в зависимости загрузки и никогда не показывает устаревшее дольше одного взгляда.
 */
export function useFresh(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let hiddenAt = 0;
    function bump() {
      setTick((value) => value + 1);
    }
    function onVisibility() {
      if (document.visibilityState === "hidden") {
        hiddenAt = Date.now();
        return;
      }
      // Мгновенное переключение вкладок не стоит запроса.
      if (hiddenAt && Date.now() - hiddenAt > 2000) bump();
    }
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener(CHANGED, bump);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener(CHANGED, bump);
    };
  }, []);
  return tick;
}
