/**
 * Видимая область экрана без экранной клавиатуры: --vv-h и --vv-top на <html>.
 * По ним чат Кипа и шторки держат поле ввода над клавиатурой (iOS не меняет 100dvh).
 * При масштабировании жестом переменные снимаются, и действует обычный 100dvh.
 */
export function trackVisualViewport(): void {
  const viewport = window.visualViewport;
  if (!viewport) return;
  const root = document.documentElement;
  let frame = 0;
  const apply = () => {
    frame = 0;
    if (Math.abs(viewport.scale - 1) > 0.01) {
      root.style.removeProperty("--vv-h");
      root.style.removeProperty("--vv-top");
      return;
    }
    root.style.setProperty("--vv-h", `${Math.round(viewport.height)}px`);
    root.style.setProperty("--vv-top", `${Math.round(viewport.offsetTop)}px`);
  };
  const schedule = () => {
    if (!frame) frame = window.requestAnimationFrame(apply);
  };
  apply();
  viewport.addEventListener("resize", schedule);
  viewport.addEventListener("scroll", schedule);
}
