import type { MetadataRoute } from "next";

import { siteUrl } from "../lib/config";

/** FR-042 — points crawlers at the sitemap and keeps them out of non-content routes. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Not secrets — a crawler simply has no reason to index either, and the
      // portal will require authentication once it exists.
      disallow: ["/portal", "/status"],
    },
    sitemap: new URL("/sitemap.xml", siteUrl()).toString(),
  };
}
