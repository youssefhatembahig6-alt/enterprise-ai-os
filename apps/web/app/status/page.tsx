import type { Metadata } from "next";

import { StatusPage } from "./StatusPage";

/**
 * Diagnostic route, not a public page.
 *
 * This is the status shell from feature 001 — how that feature demonstrates
 * FR-002 (the whole stack starts) and FR-003 (per-dependency health, including
 * the background worker). It moved here rather than being deleted with the Vite
 * SPA, because deleting it would have retired passing coverage of another
 * feature's requirements without anything noticing (research R2).
 *
 * Excluded from the sitemap and from the per-page metadata audit: it is not
 * public content, and counting it as a page would distort both.
 */
export const metadata: Metadata = {
  title: "Environment status",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <StatusPage />;
}
