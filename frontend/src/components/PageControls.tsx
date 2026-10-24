import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** DOM node inside the top bar where the current page renders its controls. */
const SlotContext = createContext<HTMLElement | null>(null);

export const PageControlsSlot = SlotContext.Provider;

/**
 * Page-level controls rendered into the top bar.
 * Layout scheme (1fr auto 1fr grid, center is truly centered):
 * left = filters, search, period navigation; center = view switchers; right = actions.
 */
export function PageControls({ left, center, right }: { left?: ReactNode; center?: ReactNode; right?: ReactNode }) {
  const slot = useContext(SlotContext);
  if (!slot) return null;
  return createPortal(
    <div className={center ? "tb-grid has-center" : "tb-grid"}>
      <div className="tb-left">{left}</div>
      <div className="tb-center">{center}</div>
      <div className="tb-right">{right}</div>
    </div>,
    slot,
  );
}
