"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@eaios/ui";

// From `session-names`, not `session`: the latter imports `next/headers`, which is
// server-only, and pulling it into a client component breaks the build.
import { CSRF_COOKIE, CSRF_HEADER } from "../../lib/session-names";

/**
 * Ending the session (spec 003 FR-027).
 *
 * Reads the readable half of the double-submit pair and echoes it in a header. The
 * session cookie itself is `httpOnly` and unreachable from here, which is the whole
 * arrangement working as intended: this component can prove it is running on the
 * site's own page, and cannot touch the credential.
 *
 * The route handler clears both cookies whatever the API answers, so this always ends
 * with the browser signed out. Navigating to `/portal` afterwards rather than to `/`
 * lands the person somewhere they can sign back in, which is what someone who has just
 * signed out of a work tool usually wants next.
 */
export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  function csrfToken(): string {
    const match = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(`${CSRF_COOKIE}=`));
    return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : "";
  }

  async function onClick(): Promise<void> {
    setBusy(true);
    try {
      await fetch("/portal/api/logout", {
        method: "POST",
        headers: { [CSRF_HEADER]: csrfToken() },
      });
    } catch {
      // The handler clears cookies before it answers, and a failed request means it
      // never ran — so fall through to the navigation either way. The worst case is a
      // server-side session that lives out its cap unused, which the absolute bound
      // exists to bound.
    }
    router.push("/portal");
    router.refresh();
  }

  return (
    <Button type="button" variant="secondary" onClick={onClick} disabled={busy}>
      {busy ? "Signing out…" : "Sign out"}
    </Button>
  );
}
