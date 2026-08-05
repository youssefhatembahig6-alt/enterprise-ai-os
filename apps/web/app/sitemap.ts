import type { MetadataRoute } from "next";

import { getNews, getVacancies } from "../lib/api";
import { siteUrl } from "../lib/config";
import { PUBLIC_PAGES } from "../lib/pages";

/**
 * FR-042 — the machine-readable index of public pages.
 *
 * `/portal` and `/status` are absent by design: neither is public content
 * (FR-001a), and `lib/pages.ts` — which this reads — excludes them.
 *
 * That list used to be repeated here as a local `staticPaths` array while the
 * end-to-end specs read a second copy of their own. The comment in this spot
 * claimed the metadata audit derived its pages from this file; it did not, and the
 * two lists were free to drift apart without anything noticing
 * (contracts/routes.md).
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const entries: MetadataRoute.Sitemap = PUBLIC_PAGES.map((path) => ({
    url: new URL(path, base).toString(),
    changeFrequency: "weekly",
  }));

  // Detail pages are listed individually so each is discoverable. A failure here
  // degrades to the static list rather than taking the sitemap down: a partial
  // sitemap is far better than none.
  try {
    const [news, vacancies] = await Promise.all([getNews(50), getVacancies()]);
    for (const item of news.items) {
      entries.push({
        url: new URL(`/news/${item.slug}`, base).toString(),
        lastModified: item.published_on,
      });
    }
    for (const vacancy of vacancies) {
      entries.push({
        url: new URL(`/careers/${vacancy.slug}`, base).toString(),
        lastModified: vacancy.posted_on,
      });
    }
  } catch {
    // Static entries still ship.
  }

  return entries;
}
