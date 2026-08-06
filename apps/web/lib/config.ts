/**
 * Where the API lives, which differs by who is asking.
 *
 * A server component runs inside the Compose network and reaches the API by its
 * service name. The browser runs on the host and reaches it through the
 * published port. Collapsing these into one value breaks whichever side is not
 * the one it was written for — and the failure looks like the API being down
 * rather than being misaddressed.
 */

/**
 * For code running on the server: route handlers and server components.
 *
 * **The only API base there is now, and that is the fix rather than a tidy-up.**
 *
 * There were three: `apiBaseServer`, `apiBaseBrowser`, and an `apiBase` that chose
 * between them by execution context. The browser-facing pair existed so client
 * components could call the API directly — which does not work. A cross-origin POST
 * with a JSON body needs a CORS preflight and the API answers `OPTIONS` with 405; a
 * cross-origin GET is sent but its response is unreadable without
 * `Access-Control-Allow-Origin`, which the API does not send. Both were verified
 * against the running stack.
 *
 * Every browser-originated call now goes to the site's own origin — `/api/contact`,
 * `/api/upstream/*`, `/portal/api/*` — and the server forwards it. So nothing in the
 * browser needs the API's address, and a function that hands one out is a way for that
 * to be reintroduced by accident.
 */
export const apiBaseServer = (): string =>
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

/** Absolute origin of the site itself — canonical URLs and the sitemap need it. */
export const siteUrl = (): string =>
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
