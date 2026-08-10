import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { SignOutButton } from "../../../components/portal/SignOutButton";
import { PortalNav } from "../../../components/portal/PortalNav";
import {
  getCurrentUser,
  SessionExpiredError,
  UnauthenticatedError,
} from "../../../lib/portal-api";

/**
 * The authenticated shell (spec 003 FR-027, FR-028).
 *
 * A route group — `(authed)` is in parentheses, so it shapes the tree without
 * appearing in any URL. `/portal` stays the sign-in address and `/portal/home` stays
 * `/portal/home`; what the group buys is one place where "you must be signed in"
 * is true for everything beneath it.
 *
 * **Identity is fetched once here and passed down.** Every page under this layout
 * needs the caller's name and permission codes, and fetching them per page would mean
 * several round trips rendering one screen — each one re-deriving the same access
 * context the server rebuilds on every request anyway (FR-004).
 *
 * **Both refusals redirect to `/portal`**, which decides between the sign-in form and
 * the expired state by looking for a cookie. That decision lives in one place rather
 * than being made again by every page, and it is the only place that *can* make it:
 * the API refuses an ended session and a missing one identically, on purpose, so only
 * the browser's own cookie distinguishes them.
 */
export default async function AuthenticatedPortalLayout({
  children,
}: {
  children: ReactNode;
}) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    // Only the two identity outcomes redirect. A bare `catch` sent a dependency
    // failure to the sign-in form too, which told a signed-in person during an outage
    // that they were signed out — collapsing *error* into *unauthenticated*, the exact
    // pair contracts/portal-routes.md §3 says must stay distinct. Anything else is
    // rethrown and met by `app/portal/error.tsx`, which is the parent segment because
    // a boundary cannot catch the layout it sits beside.
    if (error instanceof UnauthenticatedError || error instanceof SessionExpiredError) {
      redirect("/portal");
    }
    throw error;
  }

  return (
    <div className="eaios-portal">
      <header className="eaios-portal__bar">
        <PortalNav user={user} />
        <div className="eaios-portal__identity">
          <span>
            {user.full_name}
            <span className="eaios-portal__company"> · {user.company_name}</span>
          </span>
          <SignOutButton />
        </div>
      </header>

      {/*
        The heading inside each page is the focus target after a route change. Marked
        as the main landmark so a screen-reader user can jump straight here rather than
        traversing the navigation on every page.
      */}
      <main id="portal-main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
