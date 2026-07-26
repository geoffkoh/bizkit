import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type JSX,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

/** The one tooltip primitive (UI_SPECIFICATION.md §2.2 shadow-md, §2.3
 * duration-base, §2.4 disabled controls "still explain why").
 *
 * Everything that needs a hover/focus bubble goes through here:
 * - `Truncate` (grid cells, grid headers, sidebar tree labels) shows the full
 *   value of clipped text;
 * - `Tooltip` wraps any control — including a *disabled* one — to explain
 *   why it can't be used.
 *
 * The bubble renders in a portal with `position: fixed`, so it never grows a
 * row, clips against a cell's `overflow: hidden`, or disturbs a grid layout.
 * Disabled form controls swallow pointer events, hence the wrapper element:
 * the wrapper is the hover target and is focusable so keyboard users can
 * reach the explanation too.
 */

interface Anchor {
  readonly top: number;
  readonly bottom: number;
  readonly left: number;
}

const GAP_PX = 6;
const EDGE_PX = 8;

/** `:focus-visible` semantics (§2.4), with a guard for engines that reject it. */
function isFocusVisible(element: Element): boolean {
  try {
    return element.matches(":focus-visible");
  } catch {
    return true;
  }
}

function TooltipBubble({
  id,
  text,
  anchor,
}: {
  id: string;
  text: string;
  anchor: Anchor;
}): JSX.Element {
  const ref = useRef<HTMLDivElement | null>(null);
  const [style, setStyle] = useState<{ top: number; left: number }>({
    top: anchor.bottom + GAP_PX,
    left: anchor.left,
  });

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const { width, height } = node.getBoundingClientRect();
    const maxLeft = window.innerWidth - width - EDGE_PX;
    const left = Math.max(EDGE_PX, Math.min(anchor.left, maxLeft));
    const below = anchor.bottom + GAP_PX;
    const top =
      below + height > window.innerHeight - EDGE_PX
        ? Math.max(EDGE_PX, anchor.top - height - GAP_PX)
        : below;
    setStyle({ top, left });
  }, [anchor.bottom, anchor.left, anchor.top, text]);

  return createPortal(
    <div id={id} className="tooltip" role="tooltip" ref={ref} style={style}>
      {text}
    </div>,
    document.body,
  );
}

export interface TooltipHostProps {
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onFocus: (event: FocusEvent<HTMLElement>) => void;
  onBlur: () => void;
  "aria-describedby": string | undefined;
}

export interface TooltipAnchor<T extends HTMLElement> {
  /** Attach to the element the bubble should point at. */
  ref: RefObject<T | null>;
  /** Spread onto that same element. */
  hostProps: TooltipHostProps;
  /** Render next to the host (it portals itself out). */
  bubble: JSX.Element | null;
  /** True when the host sits inside a link/button that is already a tab stop. */
  nestedInInteractive: boolean;
  open: () => void;
  close: () => void;
}

/**
 * Wire a hover/focus tooltip to an element.
 *
 * @param content Text to show; an empty string disables the tooltip.
 * @param enabled Gate for conditional tooltips (e.g. only when truncated).
 */
export function useTooltip<T extends HTMLElement>(
  content: string,
  enabled = true,
  /** Set false when the host is its own focus target inside another control,
   * so focusing that control doesn't also pop this bubble. */
  attachToAncestor = true,
): TooltipAnchor<T> {
  const ref = useRef<T | null>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [nestedInInteractive, setNested] = useState(false);
  const id = useId();

  // Read at event time, so callers can flip the gate without re-wiring.
  const gate = useRef(enabled && content.length > 0);
  gate.current = enabled && content.length > 0;

  const open = useCallback(() => {
    const node = ref.current;
    if (!node || !gate.current) return;
    const rect = node.getBoundingClientRect();
    setAnchor({ top: rect.top, bottom: rect.bottom, left: rect.left });
  }, []);

  const close = useCallback(() => setAnchor(null), []);

  // Inside a link or button (sidebar tree label, grid header) the container is
  // already a tab stop: hang the tooltip off *its* focus rather than adding a
  // second, nested one.
  useEffect(() => {
    const host = ref.current?.closest("a[href], button, [role='button']");
    setNested(Boolean(host));
    if (!host || !attachToAncestor) return;
    const onFocus = () => {
      if (isFocusVisible(host)) open();
    };
    host.addEventListener("focus", onFocus);
    host.addEventListener("blur", close);
    return () => {
      host.removeEventListener("focus", onFocus);
      host.removeEventListener("blur", close);
    };
  }, [open, close, attachToAncestor]);

  // A fixed-position bubble drifts if the page scrolls underneath it.
  useEffect(() => {
    if (!anchor) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [anchor, close]);

  return {
    ref,
    hostProps: {
      onMouseEnter: open,
      onMouseLeave: close,
      onFocus: (event: FocusEvent<HTMLElement>) => {
        // `focus` bubbles in React, so the real focus owner is `target`: the
        // host itself (Truncate) or the control it wraps (a resize handle).
        const focused = event.target;
        if (focused instanceof Element && isFocusVisible(focused)) open();
      },
      onBlur: close,
      "aria-describedby": anchor ? id : undefined,
    },
    bubble: anchor ? (
      <TooltipBubble id={id} text={content} anchor={anchor} />
    ) : null,
    nestedInInteractive,
    open,
    close,
  };
}

export interface TooltipProps {
  /** The explanation. Empty string renders the children untouched. */
  content: string;
  children: ReactNode;
  className?: string;
  /**
   * Make the wrapper a tab stop. Required when wrapping a *disabled* control
   * (§2.4): the control itself can neither be hovered nor focused, so the
   * wrapper carries the affordance.
   */
  focusable?: boolean;
  /** Don't hang the bubble off an enclosing link/button's focus. */
  hoverOnly?: boolean;
}

export function Tooltip({
  content,
  children,
  className,
  focusable = false,
  hoverOnly = false,
}: TooltipProps): JSX.Element {
  const { ref, hostProps, bubble } = useTooltip<HTMLSpanElement>(
    content,
    true,
    !hoverOnly,
  );
  const classes = className ? `tooltip-host ${className}` : "tooltip-host";
  return (
    <>
      <span
        ref={ref}
        className={classes}
        tabIndex={focusable && content.length > 0 ? 0 : undefined}
        {...hostProps}
      >
        {children}
      </span>
      {bubble}
    </>
  );
}
