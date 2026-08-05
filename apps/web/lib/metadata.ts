/**
 * Per-page and per-record metadata (spec 002 FR-039 – FR-042).
 *
 * FR-039 forbids two distinct pages sharing generic placeholder metadata, so every
 * builder here takes the specifics as arguments — there is no default description
 * a page could fall back to by accident.
 */

import type { Metadata } from "next";

import { siteUrl } from "./config";

const SITE_NAME = "NileTech Solutions";

/** Trimmed to a length a search result or social card will actually show. */
export function summarize(text: string, maxLength = 155): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= maxLength) return flat;

  const cut = flat.slice(0, maxLength);
  const boundary = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf(" "));
  return `${cut.slice(0, boundary > 40 ? boundary : maxLength).trimEnd()}…`;
}

/**
 * @param path Absolute site path, used for the canonical URL (FR-042).
 */
export function pageMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  const url = new URL(path, siteUrl()).toString();
  // A title that already names the company must not have it appended again —
  // the home page produced "NileTech Solutions — … — NileTech Solutions".
  const social = title.includes(SITE_NAME) ? title : `${title} — ${SITE_NAME}`;

  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: social,
      description,
      url,
      siteName: SITE_NAME,
      type: "website",
    },
    twitter: { card: "summary", title: social, description },
  };
}

/** FR-041 — detail pages derive metadata from the record they display. */
export function articleMetadata({
  headline,
  body,
  publishedOn,
  path,
}: {
  headline: string;
  body: string;
  publishedOn: string;
  path: string;
}): Metadata {
  const base = pageMetadata({ title: headline, description: summarize(body), path });
  return {
    ...base,
    openGraph: { ...base.openGraph, type: "article", publishedTime: publishedOn },
  };
}

export function vacancyMetadata({
  title,
  description,
  officeCity,
  path,
}: {
  title: string;
  description: string;
  officeCity: string;
  path: string;
}): Metadata {
  return pageMetadata({
    title: `${title} — ${officeCity}`,
    description: summarize(description),
    path,
  });
}

/**
 * Non-content routes (`/portal`, `/status`) are excluded from indexing and from
 * the sitemap. They are not public pages, and counting them would distort the
 * per-page metadata audit FR-039 requires.
 */
export const NOT_INDEXED: Metadata = { robots: { index: false, follow: false } };
