// Vitest setup: jest-dom matchers plus the browser APIs jsdom lacks that the
// shell relies on. Importing the `/vitest` entrypoint also augments vitest's
// Assertion type, so `toBeInTheDocument()` typechecks under `tsc -b`.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// The sidebar's <900px auto-collapse reads matchMedia; jsdom has no
// implementation, so provide an inert one that reports "no match".
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// TanStack Table's column sizing and the grid's resize handle observe layout;
// jsdom never lays out, so a no-op observer keeps them from throwing.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver;
}
