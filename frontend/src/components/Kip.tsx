import { useEffect, useState } from "react";

export type KipState = "idle" | "thinking" | "talking" | "happy";

/**
 * Кип — маскот ассистента. Плоский вектор без обводки и тени, цвета брендбука:
 * тело #E97C35, хвост #C66A2D, глаза и линии ушей белые. Исходник: public/brand/kip.svg.
 * idle — дышит, моргает раз в 3–6 с, иногда ведёт ухом и машет хвостом;
 * thinking — смотрит вверх, покачивается; talking — двигает ртом; happy — подпрыгивает.
 * quiet — только моргание (аватар в ленте). prefers-reduced-motion выключает всё.
 */
export function Kip({ state = "idle", size = 40, quiet = false, className }: { state?: KipState; size?: number; quiet?: boolean; className?: string }) {
  const [blink, setBlink] = useState(false);

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
      }, 3000 + Math.random() * 3000);
    }
    plan();
    return () => {
      window.clearTimeout(timer);
      window.clearTimeout(open);
    };
  }, []);

  const classes = ["kip", `kip-${state}`, quiet ? "kip-quiet" : "", blink ? "kip-blink" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <svg className={classes} viewBox="225 250 610 610" width={size} height={size} aria-hidden="true" focusable="false">
      <g className="kip-hop">
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
          </g>
          <g className="kip-eye-right">
            <rect x="424" y="554" width="34" height="64" rx="17" fill="#FFFFFF" transform="rotate(10 441 586)" />
          </g>
        </g>
        <g className="kip-mouth">
          <ellipse cx="402" cy="650" rx="16" ry="10" fill="#FFFFFF" />
        </g>
      </g>
    </svg>
  );
}
