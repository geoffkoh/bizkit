// Vitest setup: jest-dom matchers plus the browser APIs jsdom lacks that the
// shell relies on. Importing the `/vitest` entrypoint also augments vitest's
// Assertion type, so `toBeInTheDocument()` typechecks under `tsc -b`.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Node 26 ships an *experimental* global `localStorage` that is unavailable
// unless the process was started with `--localstorage-file`, and it shadows
// the one jsdom would otherwise provide — so `localStorage.getItem` throws
// "Cannot read properties of undefined" on any component that persists a
// preference. Rather than pin the host Node or pass a flag, give the harness
// its own in-memory Storage: tests should not depend on which Node built them.
function memoryStorage(): Storage {
  const entries = new Map<string, string>();
  return {
    get length(): number {
      return entries.size;
    },
    clear: () => entries.clear(),
    getItem: (key: string) => entries.get(key) ?? null,
    key: (index: number) => [...entries.keys()][index] ?? null,
    removeItem: (key: string) => void entries.delete(key),
    setItem: (key: string, value: string) => void entries.set(key, String(value)),
  } as Storage;
}

function usable(candidate: unknown): boolean {
  try {
    (candidate as Storage | undefined)?.getItem("probe");
    return candidate != null;
  } catch {
    return false;
  }
}

for (const key of ["localStorage", "sessionStorage"] as const) {
  if (!usable(globalThis[key])) {
    const storage = memoryStorage();
    Object.defineProperty(globalThis, key, {
      value: storage,
      configurable: true,
      writable: true,
    });
    if (typeof window !== "undefined") {
      Object.defineProperty(window, key, {
        value: storage,
        configurable: true,
        writable: true,
      });
    }
  }
}

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
