import type { JSX } from "react";

/** The one icon system (UI_SPECIFICATION.md §2.1 Iconography).
 *
 * A single inline SVG symbol set (`IconSprite`, mounted once by `App`)
 * referenced through one component (`Icon`). Feather/Lucide geometry: 24×24
 * viewBox rendered at 16–18px, 1.75px stroke, round caps/joins,
 * `stroke="currentColor"` + `fill="none"` so every icon inherits text,
 * muted or semantic-state color from its context.
 *
 * Emoji and typographic glyphs are never UI chrome: pencils, eyes, sort
 * arrows, chevrons and close marks are all names in `IconName`. Adding an
 * icon means adding a symbol here, never an ad-hoc SVG (or glyph) in a
 * screen.
 */

export type IconName =
  | "alert-triangle"
  | "arrow-down"
  | "arrow-up"
  | "check"
  | "chevron-down"
  | "chevron-left"
  | "chevron-right"
  | "close"
  | "eye"
  | "folder"
  | "info"
  | "key"
  | "more-vertical"
  | "pencil"
  | "plus"
  | "search"
  | "server"
  | "sidebar"
  | "sort"
  | "spinner"
  | "trash"
  | "undo"
  | "upload"
  | "user";

const SPRITE_PREFIX = "bz-icon-";

/** Geometry per icon, in the shared 24×24 grid. */
const GLYPHS: Record<IconName, JSX.Element> = {
  "alert-triangle": (
    <>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </>
  ),
  "arrow-down": (
    <>
      <path d="M12 5v14" />
      <path d="M19 12l-7 7-7-7" />
    </>
  ),
  "arrow-up": (
    <>
      <path d="M12 19V5" />
      <path d="M5 12l7-7 7 7" />
    </>
  ),
  check: <path d="M20 6 9 17l-5-5" />,
  "chevron-down": <path d="M6 9l6 6 6-6" />,
  "chevron-left": <path d="M15 18l-6-6 6-6" />,
  "chevron-right": <path d="M9 18l6-6-6-6" />,
  close: (
    <>
      <path d="M18 6 6 18" />
      <path d="M6 6l12 12" />
    </>
  ),
  eye: (
    <>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  folder: (
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2Z" />
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </>
  ),
  key: (
    <>
      <path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4Z" />
      <path d="M16.5 7.5h.01" />
    </>
  ),
  "more-vertical": (
    <>
      <circle cx="12" cy="12" r="1" />
      <circle cx="12" cy="5" r="1" />
      <circle cx="12" cy="19" r="1" />
    </>
  ),
  pencil: (
    <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3Z" />
  ),
  plus: (
    <>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </>
  ),
  server: (
    <>
      <rect x="2" y="2" width="20" height="8" rx="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" />
      <path d="M6 6h.01" />
      <path d="M6 18h.01" />
    </>
  ),
  sidebar: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </>
  ),
  sort: (
    <>
      <path d="M7 9l5-5 5 5" />
      <path d="M7 15l5 5 5-5" />
    </>
  ),
  spinner: <path d="M21 12a9 9 0 1 1-6.219-8.56" />,
  trash: (
    <>
      <path d="M3 6h18" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </>
  ),
  undo: (
    <>
      <path d="M9 14 4 9l5-5" />
      <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
    </>
  ),
  upload: (
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M17 8l-5-5-5 5" />
      <path d="M12 3v12" />
    </>
  ),
  user: (
    <>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </>
  ),
};

const NAMES = Object.keys(GLYPHS) as IconName[];

/** The sprite itself: mounted once, near the app root. */
export function IconSprite(): JSX.Element {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={0}
      height={0}
      style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }}
    >
      {NAMES.map((name) => (
        <symbol
          key={name}
          id={`${SPRITE_PREFIX}${name}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {GLYPHS[name]}
        </symbol>
      ))}
    </svg>
  );
}

export interface IconProps {
  name: IconName;
  /** Rendered size in px (§2.1: 16–18). */
  size?: 16 | 18;
  className?: string;
  /** Accessible name; omit for purely decorative icons (default). */
  title?: string;
  /** Spin the icon (loading affordance); reduced-motion slows, never hides. */
  spin?: boolean;
}

export function Icon({
  name,
  size = 16,
  className,
  title,
  spin = false,
}: IconProps): JSX.Element {
  const classes = ["icon", spin ? "icon-spin" : null, className]
    .filter(Boolean)
    .join(" ");
  return (
    <svg
      className={classes}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      <use href={`#${SPRITE_PREFIX}${name}`} />
    </svg>
  );
}
