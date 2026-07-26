import { useEffect, useRef, useState, type JSX } from "react";
import { useTooltip } from "./Tooltip";

/** Truncate-with-tooltip (UI_SPECIFICATION.md §4.1, §3).
 *
 * Text truncates with an ellipsis at whatever width its container currently
 * has (a resized grid column, a narrowed sidebar) and the full value appears
 * in a `--shadow-md` bubble on hover or keyboard focus — but only when the
 * text is *actually* truncated, so short values stay quiet.
 *
 * Shared by grid cells, grid headers and sidebar tree labels. The bubble
 * itself comes from the one `Tooltip` primitive (`useTooltip`), never a second
 * implementation.
 */

export interface TruncateProps {
  /** The full value; also what the tooltip shows. */
  text: string;
  /** Extra classes on the truncating element (layout is the caller's job). */
  className?: string;
}

export function Truncate({ text, className }: TruncateProps): JSX.Element {
  const measureRef = useRef<HTMLSpanElement | null>(null);
  const [truncated, setTruncated] = useState(false);
  const { ref, hostProps, bubble, nestedInInteractive } =
    useTooltip<HTMLSpanElement>(text, truncated);

  // Re-measure whenever the element (or its container) resizes: a dragged
  // column edge or a narrowed sidebar changes the answer.
  useEffect(() => {
    const node = measureRef.current;
    if (!node) return;
    const measure = () => {
      setTruncated(node.scrollWidth > node.clientWidth + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [text]);

  return (
    <>
      <span
        ref={(node) => {
          measureRef.current = node;
          ref.current = node;
        }}
        className={className ? `truncate ${className}` : "truncate"}
        tabIndex={truncated && !nestedInInteractive ? 0 : undefined}
        {...hostProps}
      >
        {text}
      </span>
      {bubble}
    </>
  );
}
