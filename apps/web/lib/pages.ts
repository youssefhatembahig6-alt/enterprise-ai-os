/**
 * The site's route inventory — one declaration, read by everything (FR-001, FR-001a).
 *
 * This list was previously written out twice: `app/sitemap.ts` carried its own
 * `staticPaths`, `e2e/pages.ts` carried `PUBLIC_PAGES`, and nothing compared them.
 * The sitemap's comment even claimed the per-page metadata audit derived its list
 * from the sitemap — it did not; `e2e/metadata.spec.ts` imported the other copy. So
 * a page added to one and not the other would either be missing from the sitemap
 * crawlers read, or missing from the metadata, accessibility, responsive,
 * state-coverage, and performance sweeps that all iterate the shared list. Either
 * failure is silent.
 *
 * It lives in `lib/` rather than in `e2e/` because the application needs it: a
 * sitemap that imports from a test directory would drag test code into the build.
 */

/** The eight content pages. Every sweep that says "every page" means this. */
export const PUBLIC_PAGES = [
  "/",
  "/about",
  "/services",
  "/products",
  "/leadership",
  "/careers",
  "/news",
  "/contact",
] as const;

/**
 * FR-001a — routes that are served but are not public content. Excluded from the
 * sitemap, from the metadata audit, and from site navigation; checked for
 * behaviour instead.
 */
export const NON_CONTENT_ROUTES = ["/portal", "/status"] as const;

/**
 * The authenticated portal surfaces (spec 003 FR-027 – FR-029).
 *
 * Separate from `NON_CONTENT_ROUTES` because the sweeps treat them differently: those
 * are visited anonymously and checked for *behaviour*, while these need a session
 * before there is anything to look at. A sweep that visited these without signing in
 * would test the redirect to the sign-in form over and over and report it as coverage
 * of the portal.
 *
 * Excluded from the sitemap and marked `noindex`, exactly as the non-content routes
 * are — none of this is public content.
 *
 * `/portal` itself is deliberately **not** repeated here. It is the sign-in address,
 * reachable anonymously, and it stays in `NON_CONTENT_ROUTES` where the anonymous
 * checks already cover it (spec 002 FR-049a: the address does not change).
 */
export const PORTAL_PAGES = [
  "/portal/home",
  "/portal/profile",
  "/portal/team",
  "/portal/denied",
] as const;

/**
 * Portal routes whose address contains a parameter (spec 003 US2).
 *
 * Kept apart from `PORTAL_PAGES` rather than added to it, because the sweeps that read
 * that list navigate to each entry: a browser sent to the literal `/portal/team/[userId]`
 * would get a 404 and the sweep would report it as a portal page failing. Every consumer
 * of `PORTAL_PAGES` therefore keeps working unchanged.
 *
 * `href` builds a real address from an identifier the caller supplies, so a test drives
 * the route the way the application does — through the same function the team list
 * would use — instead of assembling the path itself and drifting from it.
 */
export const PORTAL_DYNAMIC_ROUTES = [
  {
    /** Stable identifier, so a suite can bind to the route rather than to its shape. */
    id: "team-member",
    pattern: "/portal/team/[userId]",
    href: (userId: string) => `/portal/team/${encodeURIComponent(userId)}`,
  },
] as const;

export type PublicPage = (typeof PUBLIC_PAGES)[number];
export type PortalPage = (typeof PORTAL_PAGES)[number];
export type PortalDynamicRoute = (typeof PORTAL_DYNAMIC_ROUTES)[number];
