import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { apiBaseServer } from "../../../../lib/config";
import { CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE } from "../../../../lib/session";

/**
 * Sign-out (spec 003 FR-007).
 *
 * Two properties, and the second is the one worth stating.
 *
 * **CSRF-guarded.** `SameSite=Strict` is a same-*site* policy, not a same-origin one,
 * so it does not by itself stop a request forged from another origin on the same
 * registrable domain. The double-submit check does: the caller must echo the readable
 * `eaios_csrf` cookie in a header, which an attacker who cannot read it cannot do.
 * Signing someone out is only a nuisance attack, but the guard is the same code the
 * first genuinely destructive action will need, and building it now means that action
 * inherits it rather than reinventing it.
 *
 * **The cookies are cleared regardless of what the API answers.** If the upstream call
 * fails — network, timeout, a session already ended — the browser must still end up
 * signed out. The alternative is a person who clicked "sign out", saw an error, and is
 * still holding a live credential. Server-side revocation is what actually ends
 * access (FR-007); clearing here is what makes the interface honest about it.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const store = await cookies();

  const expected = store.get(CSRF_COOKIE)?.value;
  const presented = request.headers.get(CSRF_HEADER);
  if (!expected || presented !== expected) {
    return NextResponse.json(
      { title: "Invalid request", status: 403, detail: "This request could not be verified." },
      { status: 403 },
    );
  }

  const token = store.get(SESSION_COOKIE)?.value;

  if (token) {
    try {
      await fetch(`${apiBaseServer()}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // Swallowed on purpose. The session may outlive its 8-hour cap on the server if
      // this call never lands, which is a real cost — but leaving the browser holding
      // a credential after the person asked to be signed out is a worse one, and the
      // clearing below happens either way.
    }
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(CSRF_COOKIE);
  return response;
}
