import { useEffect, useRef, useState } from "react";

// Одна точка взгляда на всё окно: мышь, перо или последнее касание. Все Кипы смотрят туда.
const gaze = { x: 0, y: 0, at: 0, touch: false };
let listeners = 0;
function onPointer(event: PointerEvent) {
  gaze.x = event.clientX;
  gaze.y = event.clientY;
  gaze.at = performance.now();
  gaze.touch = event.pointerType === "touch";
}
function watchPointer() {
  if (listeners++ === 0) {
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerdown", onPointer, { passive: true });
  }
  return () => {
    if (--listeners === 0) {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerdown", onPointer);
    }
  };
}

// Зрачок ходит внутри белка: по x до 5, по y до 16 единиц viewBox.
const REACH_X = 5;
const REACH_Y = 16;
const IDLE_MS = 4000;

export type KipState = "idle" | "thinking" | "talking" | "happy";

/**
 * Кип — маскот ассистента. Плоский вектор без обводки и тени, цвета брендбука:
 * тело #E97C35, хвост #C66A2D, глаза и линии ушей белые. Исходник: public/brand/kip.svg.
 * idle — дышит и покачивается, моргает раз в 2,5–5 с, дёргает ушами, машет хвостом;
 * thinking — наклоняет голову и водит глазами; talking — открывает рот и подпрыгивает; happy — прыгает.
 * Зрачки следят за курсором (на таче — за касанием или оглядываются). quiet — без покачиваний.
 * prefers-reduced-motion выключает всё, зрачки по центру.
 */
export function Kip({ state = "idle", size = 40, quiet = false, className }: { state?: KipState; size?: number; quiet?: boolean; className?: string }) {
  const [blink, setBlink] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  // Зрачки следят за курсором по всему окну, плавно (lerp на rAF). На тач-экране — за последним
  // касанием, без касаний — сами оглядываются. prefers-reduced-motion: зрачки по центру.
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const stop = watchPointer();
    let frame = 0;
    let x = 0;
    let y = 0;
    let wander = { x: 0, y: 0, until: 0 };
    function tick(now: number) {
      const svg = svgRef.current;
      if (svg) {
        let tx = 0;
        let ty = 0;
        const fresh = gaze.at > 0 && (!gaze.touch || now - gaze.at < IDLE_MS);
        if (fresh) {
          const box = svg.getBoundingClientRect();
          const dx = gaze.x - (box.left + box.width * 0.36);
          const dy = gaze.y - (box.top + box.height * 0.55);
          const dist = Math.hypot(dx, dy) || 1;
          const pull = Math.min(1, dist / 160);
          tx = (dx / dist) * REACH_X * pull;
          ty = (dy / dist) * REACH_Y * pull;
        } else {
          if (now > wander.until) {
            const calm = Math.random() < 0.4;
            wander = {
              x: calm ? 0 : (Math.random() * 2 - 1) * REACH_X,
              y: calm ? 0 : (Math.random() * 2 - 1) * REACH_Y * 0.6,
              until: now + 1200 + Math.random() * 2200,
            };
          }
          tx = wander.x;
          ty = wander.y;
        }
        x += (tx - x) * 0.14;
        y += (ty - y) * 0.14;
        const shift = `translate(${x.toFixed(2)} ${y.toFixed(2)})`;
        svg.querySelectorAll(".kip-pupil").forEach((pupil) => pupil.setAttribute("transform", shift));
      }
      frame = window.requestAnimationFrame(tick);
    }
    frame = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frame);
      stop();
    };
  }, []);

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    let timer = 0;
    let open = 0;
    function plan() {
      timer = window.setTimeout(() => {
        setBlink(true);
        open = window.setTimeout(() => {
          setBlink(false);
          plan();
        }, 140);
      }, 2500 + Math.random() * 2500);
    }
    plan();
    return () => {
      window.clearTimeout(timer);
      window.clearTimeout(open);
    };
  }, []);

  const classes = ["kip", `kip-${state}`, quiet ? "kip-quiet" : "", blink ? "kip-blink" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <svg ref={svgRef} className={classes} viewBox="225 250 610 610" width={size} height={size} aria-hidden="true" focusable="false">
      <g className="kip-hop">
        <g className="kip-breathe">
        <g className="kip-tail" fill="#C66A2D">
          <path d="M698 726C770 742 830 704 828 640C826 588 790 564 754 574C722 584 708 622 704 660Z" />
        </g>
        <g className="kip-body" fill="#E97C35">
          <path d="M495 410C596 408 656 426 696 482C740 542 756 624 746 686C736 750 656 776 495 776C334 776 254 750 244 686C234 624 250 542 294 482C334 426 394 412 495 410Z" />
        </g>
        <g className="kip-ear-left">
          <path fill="#E97C35" d="M282 512C276 452 282 392 296 360C305 340 326 335 345 348C382 373 420 400 452 434Z" />
          <path d="M316 436C312 410 314 388 322 374C344 386 362 398 378 412" fill="none" stroke="#FFFFFF" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        </g>
        <g className="kip-ear-right">
          <path fill="#E97C35" d="M708 512C714 452 708 392 694 360C685 340 664 335 645 348C608 373 570 400 538 434Z" />
          <path d="M674 436C678 410 676 388 668 374C646 386 628 398 612 412" fill="none" stroke="#FFFFFF" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        </g>
        <g className="kip-eyes">
          <g className="kip-eye-left">
            <rect x="341" y="550" width="34" height="64" rx="17" fill="#FFFFFF" transform="rotate(10 358 582)" />
            <circle className="kip-pupil" cx="358" cy="584" r="11" fill="#2A1A10" />
          </g>
          <g className="kip-eye-right">
            <rect x="424" y="554" width="34" height="64" rx="17" fill="#FFFFFF" transform="rotate(10 441 586)" />
            <circle className="kip-pupil" cx="441" cy="588" r="11" fill="#2A1A10" />
          </g>
        </g>
        <g className="kip-mouth">
          <ellipse cx="402" cy="650" rx="16" ry="10" fill="#FFFFFF" />
        </g>
        </g>
      </g>
    </svg>
  );
}
