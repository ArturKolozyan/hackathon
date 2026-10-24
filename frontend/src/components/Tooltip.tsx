import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const TIP_ID = "app-hint";
const GAP = 8;
const EDGE = 8;

type Tip = { text: string; rect: DOMRect };

function hintTarget(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null;
  const el = node.closest<HTMLElement>("[data-hint]");
  if (!el || !el.dataset.hint) return null;
  return el;
}

function describe(el: HTMLElement, on: boolean) {
  const ids = (el.getAttribute("aria-describedby") ?? "").split(/\s+/).filter((id) => id && id !== TIP_ID);
  if (on) ids.push(TIP_ID);
  if (ids.length) el.setAttribute("aria-describedby", ids.join(" "));
  else el.removeAttribute("aria-describedby");
}

/**
 * One global, instant tooltip for every element with `data-hint`.
 * Shows on mouse hover (no delay) and keyboard focus, never on touch. Portal, flips to stay in the viewport,
 * wires aria-describedby to the hovered/focused element.
 */
export function HintLayer() {
  const [tip, setTip] = useState<Tip | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; place: "below" | "above" } | null>(null);
  const current = useRef<HTMLElement | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const coarse = window.matchMedia("(hover: none)");

    function show(el: HTMLElement) {
      if (current.current && current.current !== el) describe(current.current, false);
      current.current = el;
      describe(el, true);
      setTip({ text: el.dataset.hint ?? "", rect: el.getBoundingClientRect() });
    }

    function hide() {
      if (current.current) describe(current.current, false);
      current.current = null;
      setTip(null);
      setPos(null);
    }

    function onOver(event: PointerEvent) {
      if (event.pointerType !== "mouse" || coarse.matches) return;
      const el = hintTarget(event.target);
      if (el) {
        if (el !== current.current) show(el);
      } else if (current.current) hide();
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
      show(el);
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") hide();
    }

    document.addEventListener("pointerover", onOver);
    document.addEventListener("pointerout", onOut);
    document.addEventListener("pointerdown", hide);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", hide);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      document.removeEventListener("pointerover", onOver);
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
    const { rect } = tip;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = rect.left + rect.width / 2 - box.width / 2;
    left = Math.max(EDGE, Math.min(left, vw - box.width - EDGE));
    let place: "below" | "above" = "below";
    let top = rect.bottom + GAP;
    if (top + box.height > vh - EDGE && rect.top - GAP - box.height >= EDGE) {
      place = "above";
      top = rect.top - GAP - box.height;
    }
    // Sidebar items: prefer the right side so the tip never covers neighbours.
    if (current.current?.closest(".nav, .sidebar-foot")) {
      const sideLeft = rect.right + GAP;
      if (sideLeft + box.width <= vw - EDGE) {
        left = sideLeft;
        top = Math.max(EDGE, Math.min(rect.top + rect.height / 2 - box.height / 2, vh - box.height - EDGE));
      }
    }
    setPos({ top, left, place });
  }, [tip]);

  if (!tip) return null;
  return createPortal(
    <div
      ref={boxRef}
      id={TIP_ID}
      role="tooltip"
      className={pos ? `hint-tip is-${pos.place}` : "hint-tip"}
      style={pos ? { top: pos.top, left: pos.left } : { top: -9999, left: -9999 }}
    >
      {tip.text}
    </div>,
    document.body,
  );
}
