import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const TIP_ID = "app-hint";
const CURSOR_GAP = 14;
const FOCUS_GAP = 8;
const EDGE = 8;

/**
 * Hints only where they help: buttons, links in the sidebar, and toggles.
 * Fields, labels and plain text never show a floating hint.
 */
const ALLOWED = "button:not(.field-btn), a, [role='switch'], [role='tab'], .team-switch .field-btn";

type Anchor = { kind: "cursor"; x: number; y: number } | { kind: "element"; rect: DOMRect };
type Tip = { text: string; anchor: Anchor; side: boolean };

function hintTarget(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null;
  const el = node.closest<HTMLElement>("[data-hint]");
  if (!el || !el.dataset.hint) return null;
  if (!el.matches(ALLOWED)) return null;
  if ((el as HTMLButtonElement).disabled && !el.closest(".nav")) return null;
  return el;
}

function describe(el: HTMLElement, on: boolean) {
  const ids = (el.getAttribute("aria-describedby") ?? "").split(/\s+/).filter((id) => id && id !== TIP_ID);
  if (on) ids.push(TIP_ID);
  if (ids.length) el.setAttribute("aria-describedby", ids.join(" "));
  else el.removeAttribute("aria-describedby");
}

/**
 * One global tooltip for every allowed element with `data-hint`.
 * Mouse: appears at once and floats with the cursor. Keyboard focus: pinned under the element.
 * Touch and pen: never. Portal, stays inside the viewport, wires aria-describedby.
 */
export function HintLayer() {
  const [tip, setTip] = useState<Tip | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const current = useRef<HTMLElement | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const coarse = window.matchMedia("(hover: none)");

    function show(el: HTMLElement, anchor: Anchor) {
      if (current.current && current.current !== el) describe(current.current, false);
      current.current = el;
      describe(el, true);
      setTip({ text: el.dataset.hint ?? "", anchor, side: false });
    }

    function hide() {
      if (current.current) describe(current.current, false);
      current.current = null;
      setTip(null);
      setPos(null);
    }

    function onMove(event: PointerEvent) {
      if (event.pointerType !== "mouse" || coarse.matches) return;
      const el = hintTarget(event.target);
      if (!el) {
        if (current.current) hide();
        return;
      }
      const anchor: Anchor = { kind: "cursor", x: event.clientX, y: event.clientY };
      if (el !== current.current) {
        show(el, anchor);
        return;
      }
      if (frame.current !== null) return;
      frame.current = window.requestAnimationFrame(() => {
        frame.current = null;
        setTip((prev) => (prev ? { ...prev, text: el.dataset.hint ?? prev.text, anchor } : prev));
      });
    }

    function onOut(event: PointerEvent) {
      if (!current.current) return;
      const next = event.relatedTarget;
      if (next instanceof Node && current.current.contains(next)) return;
      if (hintTarget(next) === current.current) return;
      hide();
    }

    function onFocus(event: FocusEvent) {
      const el = hintTarget(event.target);
      if (!el || !(event.target as Element).matches(":focus-visible")) return;
      show(el, { kind: "element", rect: el.getBoundingClientRect() });
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") hide();
    }

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerout", onOut);
    document.addEventListener("pointerdown", hide);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", hide);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerout", onOut);
      document.removeEventListener("pointerdown", hide);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, []);

  useLayoutEffect(() => {
    if (!tip || !boxRef.current) return;
    const box = boxRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left: number;
    let top: number;
    if (tip.anchor.kind === "cursor") {
      const { x, y } = tip.anchor;
      left = x + CURSOR_GAP;
      top = y + CURSOR_GAP + 4;
      // Не помещается справа — слева от курсора; снизу — над курсором.
      if (left + box.width > vw - EDGE) left = x - CURSOR_GAP - box.width;
      if (top + box.height > vh - EDGE) top = y - CURSOR_GAP - box.height;
    } else {
      const { rect } = tip.anchor;
      left = rect.left + rect.width / 2 - box.width / 2;
      top = rect.bottom + FOCUS_GAP;
      if (top + box.height > vh - EDGE && rect.top - FOCUS_GAP - box.height >= EDGE) {
        top = rect.top - FOCUS_GAP - box.height;
      }
    }
    left = Math.max(EDGE, Math.min(left, vw - box.width - EDGE));
    top = Math.max(EDGE, Math.min(top, vh - box.height - EDGE));
    setPos({ top, left });
  }, [tip]);

  if (!tip) return null;
  return createPortal(
    <div
      ref={boxRef}
      id={TIP_ID}
      role="tooltip"
      className={pos ? "hint-tip is-shown" : "hint-tip"}
      style={pos ? { transform: `translate3d(${Math.round(pos.left)}px, ${Math.round(pos.top)}px, 0)` } : { transform: "translate3d(-9999px, -9999px, 0)" }}
    >
      {tip.text}
    </div>,
    document.body,
  );
}
