"use client";

import Link from "next/link";

/**
 * FR-029 — the Server Error page.
 *
 * It receives the error object and deliberately renders **nothing** from it. No
 * message, no stack, no digest. Those carry hostnames, query text, and internal
 * identifiers, and a visitor can do nothing with any of it. `reset` is offered
 * because a transient failure is worth one retry.
 *
 * Must be a client component — that is Next's contract for an error boundary.
 */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>Something went wrong on our side</h1>
      <p>
        We could not load this page. The problem is ours, not yours, and we have recorded
        it.
      </p>
      <div className="eaios-actions">
        <button type="button" className="eaios-button" onClick={reset}>
          Try again
        </button>
        <Link href="/" className="eaios-button eaios-button--secondary">
          Go to the home page
        </Link>
      </div>
    </div>
  );
}
