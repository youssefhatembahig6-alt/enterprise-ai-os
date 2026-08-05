import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Tag, Text } from "@eaios/ui";

import { NotFoundError, getVacancy } from "../../../lib/api";
import { vacancyMetadata } from "../../../lib/metadata";

type Props = { params: Promise<{ slug: string }> };

/**
 * FR-041 — metadata derived from the record shown, not from a page template.
 *
 * A missing vacancy returns empty metadata rather than throwing: Next renders the
 * not-found page, and this function must not be the thing that fails first.
 */
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  try {
    const vacancy = await getVacancy(slug);
    return vacancyMetadata({
      title: vacancy.title,
      description: vacancy.description,
      officeCity: vacancy.office_city,
      path: `/careers/${slug}`,
    });
  } catch {
    return {};
  }
}

export default async function VacancyPage({ params }: Props) {
  const { slug } = await params;

  let vacancy: Awaited<ReturnType<typeof getVacancy>>;
  try {
    vacancy = await getVacancy(slug);
  } catch (error) {
    // A slug belonging to the other tenant lands here too, which is correct: the
    // visitor learns nothing about whether it exists elsewhere.
    if (error instanceof NotFoundError) notFound();
    throw error;
  }

  return (
    <article>
      <p>
        <Link href="/careers">← All open roles</Link>
      </p>

      <h1>{vacancy.title}</h1>

      <p>
        <Tag>{vacancy.department}</Tag>{" "}
        <Tag>
          {vacancy.office_city}, {vacancy.office_country}
        </Tag>
      </p>

      <p>
        Posted <time dateTime={vacancy.posted_on}>{vacancy.posted_on}</time>
      </p>

      <section className="eaios-section" aria-labelledby="role-description">
        <h2 id="role-description">About the role</h2>
        <p><Text value={vacancy.description} /></p>
      </section>

      <Link href="/contact" className="eaios-button">
        Apply through our contact form
      </Link>
    </article>
  );
}
