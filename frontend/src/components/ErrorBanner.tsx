import { useEffect, useState, type JSX } from "react";
import { Icon } from "./Icon";

/** The app-level fetch-failure banner (UI_SPECIFICATION.md §6 Errors).
 *
 * "Global fetch failures as a dismissible banner": this is for *queries* —
 * the app couldn't load something. Mutation failures stay inline next to the
 * control that triggered them (plus a toast), never here.
 *
 * Driven from the QueryClient's cache callbacks in `main.tsx`, so no screen
 * has to remember to report anything: one banner, one message (the latest),
 * cleared automatically as soon as any query succeeds again.
 */

type Listener = (message: string | null) => void;

let current: string | null = null;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener(current);
}

export function reportQueryFailure(message: string): void {
  if (current === message) return;
  current = message;
  emit();
}

export function clearQueryFailure(): void {
  if (current === null) return;
  current = null;
  emit();
}

export function ErrorBannerHost(): JSX.Element | null {
  const [message, setMessage] = useState<string | null>(current);
  useEffect(() => {
    listeners.add(setMessage);
    return () => {
      listeners.delete(setMessage);
    };
  }, []);
  if (message === null) return null;
  return (
    <div className="banner" role="alert">
      <Icon name="alert-triangle" size={16} />
      <span className="banner-message">{message}</span>
      <button
        type="button"
        className="icon-button"
        onClick={() => clearQueryFailure()}
      >
        <Icon name="close" size={16} title="Dismiss" />
      </button>
    </div>
  );
}
