/**
 * Re-exported from the application so the specs and the sitemap cannot disagree
 * about what the site contains (FR-001, FR-001a).
 *
 * Kept as a module rather than replaced by a direct import at each call site: the
 * specs referred to `./pages` in seven places, and this is the one file that has to
 * know where the list actually lives.
 */
export { NON_CONTENT_ROUTES, PUBLIC_PAGES, type PublicPage } from "../lib/pages";
