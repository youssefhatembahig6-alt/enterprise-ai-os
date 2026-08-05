import type { ReactNode } from "react";

/**
 * FR-008a — generated content at any length the dataset produces.
 *
 * Two cases, and the distinction is the whole requirement. Content that is **short
 * but present** — a one-word service summary, a single-sentence biography — is
 * legitimate data and renders as written. A field that is **empty or whitespace-only**
 * would otherwise render as nothing at all, leaving a heading above a gap that a
 * visitor reads as a broken card. That is the blank region FR-026 forbids for empty
 * states, arriving through a different door.
 *
 * The fallback is marked up rather than injected as text: an em dash on its own is
 * meaningless to a screen reader, so the visible glyph is hidden from assistive
 * technology and a real phrase is announced instead.
 *
 * Deliberately a presentation rule and not a data rule. Nothing here hides a record
 * or constrains the generator — FR-011 and FR-013 require *every* record to be
 * listed, so a profile with a thin biography still appears.
 */
export function Text({
  value,
  fallback = "Not provided",
}: {
  value: string | null | undefined;
  /** Overridable so a field can say something more useful than the default. */
  fallback?: string;
}): ReactNode {
  if (value !== null && value !== undefined && value.trim() !== "") return value;

  return (
    <span className="eaios-text--absent">
      <span aria-hidden="true">—</span>
      <span className="sr-only">{fallback}</span>
    </span>
  );
}
