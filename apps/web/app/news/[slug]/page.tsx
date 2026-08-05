import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Text } from "@eaios/ui";

import { NotFoundError, getNewsItem } from "../../../lib/api";
import { articleMetadata } from "../../../lib/metadata";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  try {
    const item = await getNewsItem(slug);
    return articleMetadata({
      headline: item.headline,
      body: item.body,
      publishedOn: item.published_on,
      path: `/news/${slug}`,
    });
  } catch {
    return {};
  }
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;

  let item: Awaited<ReturnType<typeof getNewsItem>>;
  try {
    item = await getNewsItem(slug);
  } catch (error) {
    if (error instanceof NotFoundError) notFound();
    throw error;
  }

  return (
    <article>
      <p>
        <Link href="/news">← All news</Link>
      </p>

      <h1>{item.headline}</h1>

      <p>
        <time dateTime={item.published_on}>{item.published_on}</time>
      </p>

      {/* Split on blank lines so generated prose keeps its paragraphs. Rendered as
          text, never as markup — the body is generated content, and treating it as
          HTML would be a habit worth not forming. */}
      {item.body.trim() === "" ? (
        // FR-008a. Splitting an empty string yields `['']`, so the map alone
        // rendered one empty paragraph under the headline — the blank region the
        // requirement forbids. T133 routed thirteen fields through `Text` and missed
        // this one: it renders a *list* rather than a single value, which is exactly
        // the shape a search for bare `{field}` interpolations does not match.
        <p>
          <Text value={item.body} fallback="No further detail was published." />
        </p>
      ) : (
        item.body.split(/\n\s*\n/).map((paragraph, index) => (
          <p key={index}>{paragraph.trim()}</p>
        ))
      )}
    </article>
  );
}
