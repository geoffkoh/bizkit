import { useEffect, useRef, useState, type JSX } from "react";
import { Icon, type IconName } from "./Icon";

/** The one toast system (UI_SPECIFICATION.md §6).
 *
 * A single app-level stack: top-right, `--shadow-md`, slide+fade in over
 * `--duration-base`/`--easing-enter`, auto-dismiss after ~4s with a shrinking
 * progress bar, each individually dismissible.
 *
 * `showToast` is a plain module function, not a hook, so TanStack Query
 * mutation `onSuccess`/`onError` handlers can call it directly:
 *
 * ```ts
 * useMutation({
 *   mutationFn: () => api.submit(id),
 *   onSuccess: () => showToast("Submitted for review", "success"),
 *   onError: (e) => showToast(String(e), "error"),
 * });
 * ```
 *
 * Toasts are a *supplement* to inline errors, never a replacement: a 403 or a
 * validation failure still renders next to the control that triggered it.
 */

export type ToastVariant = "success" | "error" | "info";

export interface Toast {
  readonly id: number;
  readonly message: string;
  readonly variant: ToastVariant;
}

/** How long a toast lives before it auto-dismisses (matches --duration-toast). */
const TOAST_TTL_MS = 4000;
/** Exit animation window (matches --duration-base). */
const TOAST_EXIT_MS = 160;
/** Ceiling on simultaneous toasts; the oldest is dropped first. */
const MAX_TOASTS = 4;

type Listener = (toasts: readonly Toast[]) => void;

let toasts: readonly Toast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener(toasts);
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Remove a toast immediately (used by the close button and the TTL timer). */
export function dismissToast(id: number): void {
  const next = toasts.filter((t) => t.id !== id);
  if (next.length !== toasts.length) {
    toasts = next;
    emit();
  }
}

/**
 * Queue a toast. Returns its id so a caller can dismiss it early.
 *
 * @param message Human-readable, already-formatted text.
 * @param variant `success` | `error` | `info` (default `info`).
 */
export function showToast(
  message: string,
  variant: ToastVariant = "info",
): number {
  const id = nextId++;
  const queued = [...toasts, { id, message, variant }];
  toasts = queued.slice(Math.max(0, queued.length - MAX_TOASTS));
  emit();
  return id;
}

const VARIANT_ICON: Record<ToastVariant, IconName> = {
  success: "check",
  error: "alert-triangle",
  info: "info",
};

function ToastItem({ toast }: { toast: Toast }): JSX.Element {
  const [leaving, setLeaving] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const fade = window.setTimeout(() => setLeaving(true), TOAST_TTL_MS);
    const drop = window.setTimeout(
      () => dismissToast(toast.id),
      TOAST_TTL_MS + TOAST_EXIT_MS,
    );
    timers.current = [fade, drop];
    return () => {
      for (const t of timers.current) window.clearTimeout(t);
    };
  }, [toast.id]);

  return (
    <div className={`toast toast-${toast.variant} ${leaving ? "leaving" : ""}`}>
      <span className="toast-icon">
        <Icon name={VARIANT_ICON[toast.variant]} size={16} />
      </span>
      <span className="toast-message">{toast.message}</span>
      <button
        type="button"
        className="icon-button"
        onClick={() => dismissToast(toast.id)}
      >
        <Icon name="close" size={16} title="Dismiss notification" />
      </button>
      <span className="toast-progress" />
    </div>
  );
}

/** The stack host. Mount exactly once, at the app root. */
export function ToastHost(): JSX.Element | null {
  const [items, setItems] = useState<readonly Toast[]>(toasts);
  useEffect(() => subscribe(setItems), []);
  if (items.length === 0) return null;
  return (
    <div
      className="toast-stack"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {items.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
