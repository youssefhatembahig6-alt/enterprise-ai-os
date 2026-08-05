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

export type PublicPage = (typeof PUBLIC_PAGES)[number];
