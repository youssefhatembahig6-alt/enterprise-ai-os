"use client";

import Link from "next/link";

import { ErrorState } from "@eaios/ui";

/**
 * The portal's error boundary (spec 003 FR-022, FR-029; contracts/portal-routes.md §3).
 *
 * **At `app/portal/`, not inside `(authed)`, and the placement is the whole point.**
 * Next does not let an `error.tsx` catch a throw from the `layout.tsx` beside it — the
 * boundary is rendered *by* that layout, so it is already gone. The authenticated
 * shell fetches the caller's identity in its own layout, so a boundary in the same
 * segment could never catch the one failure most worth catching. One segment up, this
 * one can: it wraps the group, so it catches the shell and every page under it.
 *
 * It renders nothing from the error. No message, no digest, no status code — those
 * carry hostnames, query text, and identifiers, and FR-022 keeps all of it out of what
 * a caller sees. The audit trail keeps the truth the screen withholds.
 *
 * **It says nothing about whether the caller is signed in**, in either direction. This
 * boundary catches failures from the shell as well as from the pages beneath it, and a
 * shell failure happens *before* identity is known — so "you are still signed in" would
 * be a guess, and the wrong one whenever the session had in fact ended.
 *
 * `reset` is passed to `ErrorState.retry`, which is what that prop is for: a
 * visitor-initiated retry that re-renders the segment rather than reloading the tab.
 * The prop existed unused for the whole of feature 002 and §3 says so by name.
 */
export default function PortalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>The portal could not be loaded</h1>

      <ErrorState
        title="Something went wrong on our side"
        retry={
          <>
            <button type="button" className="eaios-button" onClick={reset}>
              Try again
            </button>
            <Link href="/portal/home" className="eaios-button eaios-button--secondary">
              Back to the portal
            </Link>
          </>
        }
      >
        <p>
          The portal could not be loaded. Trying again often works; if it does not, the
          IT team can help.
        </p>
      </ErrorState>
    </div>
  );
}
