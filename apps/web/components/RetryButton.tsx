"use client";

import { Button } from "@eaios/ui";

/**
 * FR-027's manual retry.
 *
 * Every error state on this site previously read "Please refresh to try again",
 * which tells the visitor to perform the retry rather than offering one — and
 * `ErrorState` had carried an unused `retry` prop since it was written. The
 * requirement is an affordance.
 *
 * A full document reload rather than a router refresh, because these are
 * server-rendered regions: the content the visitor is missing is fetched during the
 * server render, so re-requesting the document is exactly the operation that would
 * produce it. `location.reload()` also needs no router context, which keeps this
 * renderable in the component tests that sweep every page's error state.
 *
 * Visitor-initiated, never automatic. FR-027 is explicit: a site that retried on its
 * own would multiply requests against the dependency that is already failing.
 */
export function RetryButton({ label = "Try again" }: { label?: string }) {
  return (
    <Button variant="secondary" type="button" onClick={() => window.location.reload()}>
      {label}
    </Button>
  );
}
