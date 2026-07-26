// One place that turns a thrown error into user-facing copy
// (UI_SPECIFICATION.md §6 Errors).
//
// The 403 wording is fixed by the spec: affordances can be stale, enforcement
// is server-side, so the message names the server as the one saying no. 409
// (state-machine conflict) reads the same way — the server declined because
// the changeset moved underneath us.

import { ApiError } from "./api";

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403 || error.status === 409) {
      return `The server declined: ${error.message}`;
    }
    if (error.status === 404) {
      return `Not found: ${error.message}`;
    }
    return `Request failed (${error.status}): ${error.message}`;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
