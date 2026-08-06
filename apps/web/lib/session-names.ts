/**
 * Cookie and header names, importable from anywhere.
 *
 * Separate from `lib/session.ts` for a reason the build enforces: that module imports
 * `next/headers`, which is server-only, so a client component importing a *constant*
 * from it drags the server module into the client bundle and the build fails with
 * "You're importing a component that needs next/headers".
 *
 * `SignOutButton` is a client component and needs these names to read the CSRF cookie
 * and set the header. It cannot need anything else from that file, and now it cannot
 * accidentally acquire a dependency on one.
 */

/** The session cookie. `httpOnly` — named here, never readable from the browser. */
export const SESSION_COOKIE = "eaios_session";

/**
 * The double-submit CSRF token. Deliberately readable by JavaScript: the client echoes
 * it in a header, and an attacker on another origin can cause the cookie to be *sent*
 * without being able to *read* it.
 */
export const CSRF_COOKIE = "eaios_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
