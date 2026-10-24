import type { CSSProperties, ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * «‹ Октябрь 2026 ›»: arrows on both sides of the period, the middle has a stable width
 * (`width` in rem) so the arrows never jump when the label changes length.
 */
export function PeriodNav({
  label,
  prevLabel,
  nextLabel,
  prevHint,
  nextHint,
  onPrev,
  onNext,
  disabled,
  width,
  children,
}: {
  label: string;
  prevLabel: string;
  nextLabel: string;
  prevHint: string;
  nextHint: string;
  onPrev: () => void;
  onNext: () => void;
  disabled?: boolean;
  /** Width of the middle part, e.g. "10.5rem". */
  width: string;
  children: ReactNode;
}) {
  return (
    <div className="period-nav" role="group" aria-label={label} style={{ "--period-w": width } as CSSProperties}>
      <button type="button" className="icon-btn" aria-label={prevLabel} data-hint={prevHint} disabled={disabled} onClick={onPrev}>
        <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
      </button>
      <div className="period-nav-mid">{children}</div>
      <button type="button" className="icon-btn" aria-label={nextLabel} data-hint={nextHint} disabled={disabled} onClick={onNext}>
        <ChevronRight size={18} strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  );
}
