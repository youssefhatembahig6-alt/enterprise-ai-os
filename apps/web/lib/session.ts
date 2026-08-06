import { cookies } from "next/headers";

/**
 * Reading the session on the server (spec 003 research R3).
 *
 * The token lives in an `httpOnly` cookie. Browser JavaScript cannot read it — that is
 * the point, and it is the version of "do not put tokens in localStorage" that a
 * browser enforces rather than one a future component can quietly break.
 *
 * The consequence is this module. A `fetch` from a server component does **not**
 * inherit the browser's cookie jar; the cookie arrives at the Next.js server, and
 * anything calling the API onward has to attach it by hand. Forgetting that produces
 * the confusing failure where a page renders signed-out on the server and signed-in in
 * the browser, and the only symptom is a 401 nobody can reproduce by clicking.
 */

import { SESSION_COOKIE } from "./session-names";

// Re-exported so server code has one import for everything session-related. The names
// themselves live in a module with no server-only imports, because client components
// need them too — see `session-names.ts`.
export { CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE } from "./session-names";

/** The bearer token for this request, or null when nobody is signed in. */
export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/**
 * Headers that carry the caller's identity to the API.
 *
 * Returns null rather than empty headers when there is no session, so a caller has to
 * decide what to do about it. Silently sending an unauthenticated request would turn
 * "not signed in" into "401 from the API", which is the same outcome by a longer route
 * and one more place for the reason to get lost.
 */
export async function authHeaders(): Promise<Record<string, string> | null> {
  const token = await sessionToken();
  return token ? { Authorization: `Bearer ${token}` } : null;
}
