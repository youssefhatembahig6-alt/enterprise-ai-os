import { Skeleton } from "@eaios/ui";

/**
 * The authenticated portal's loading state (spec 003 FR-029; contracts/portal-routes.md §3).
 *
 * §3 asks for "a skeleton matching the final layout, never a spinner over a blank page".
 * Placed in the `(authed)` route group so one file serves every surface beneath it —
 * home, profile, team, the team member page, and denied. A per-route `loading.tsx`
 * would be five copies of the same shape, and the sixth route added would have none.
 *
 * **It sits inside the group, not at `app/portal/`, on purpose.** Next wraps a
 * segment's *children* in the Suspense boundary this file declares, so this covers the
 * pages. `/portal` itself is the sign-in address and is deliberately outside the
 * group: it renders a form, not fetched data, and has its own submitting state.
 *
 * The shape mirrors what resolves into it — a page heading, a line of context, then a
 * body — so the layout does not jump when the real content arrives.
 *
 * `Skeleton` is `aria-hidden`; announcing a shimmering box tells a screen-reader user
 * nothing. The status region beside it is what gets announced, and it is `role="status"`
 * rather than `alert` because waiting is not an error.
 */
export default function PortalLoading() {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <p className="sr-only" role="status">
        Loading your portal…
      </p>
      <Skeleton lines={5} />
    </div>
  );
}
