import type { Metadata } from "next";
import Link from "next/link";

import { Card } from "@eaios/ui";

import { Section } from "../../components/Section";
import { getNews } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "News",
  description: "Announcements and updates from NileTech Solutions.",
  path: "/news",
});

/** FR-016 — every generated item, newest first, all of them reachable. */
export default function NewsPage() {
  return (
    <>
      <h1>News</h1>
      <p className="eaios-hero__lede">What we have been building, shipping, and learning.</p>

      <Section
        title="Announcements"
        id="news-list"
        // 50 is the endpoint's ceiling; the dataset holds far fewer, so every item
        // is reachable on one page and FR-016 is satisfied without pagination.
        load={async () => (await getNews(50)).items}
        empty={{
          title: "No announcements yet",
          body: "There is nothing to report just now. Check back soon.",
        }}
      >
        {(items) =>
          items.map((item) => (
            <Card key={item.slug} title={item.headline}>
              <p>
                <time dateTime={item.published_on}>{item.published_on}</time>
              </p>
              <Link href={`/news/${item.slug}`}>Read the announcement</Link>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
