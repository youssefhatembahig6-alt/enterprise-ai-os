/**
 * Where the API lives, which differs by who is asking.
 *
 * A server component runs inside the Compose network and reaches the API by its
 * service name. The browser runs on the host and reaches it through the
 * published port. Collapsing these into one value breaks whichever side is not
 * the one it was written for — and the failure looks like the API being down
 * rather than being misaddressed.
 */

/** For code running in the browser. Must be inlined at build time, hence NEXT_PUBLIC_. */
export const apiBaseBrowser = (): string =>
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** For code running on the server (route handlers, server components). */
export const apiBaseServer = (): string =>
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

/**
 * Whichever base the *caller* can actually reach.
 *
 * `submitContact` runs in the browser (the form is a client component) but is
 * defined beside the server-side readers. Picking the base by execution context
 * keeps one function correct in both places; hard-coding either one makes it fail
 * in the other, and the failure reads as the API being down.
 */
export const apiBase = (): string =>
  typeof window === "undefined" ? apiBaseServer() : apiBaseBrowser();

/** Absolute origin of the site itself — canonical URLs and the sitemap need it. */
export const siteUrl = (): string =>
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
