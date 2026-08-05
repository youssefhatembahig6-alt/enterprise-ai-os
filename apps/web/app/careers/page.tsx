import type { Metadata } from "next";
import Link from "next/link";

import { Card, EmptyState, ErrorState, Tag } from "@eaios/ui";

import { RetryButton } from "../../components/RetryButton";
import { VacancyFilters } from "../../components/VacancyFilters";
import { getVacancies } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "Careers",
  description: "Open roles at NileTech Solutions in Cairo, Alexandria, and Dubai.",
  path: "/careers",
});

/**
 * FR-014 — every open vacancy, filterable by office and team.
 *
 * Closed vacancies never arrive: the API filters them out server-side, so there is
 * no state here that could be misread.
 */
export default async function CareersPage({
  searchParams,
}: {
  searchParams: Promise<{ office?: string; department?: string }>;
}) {
  const { office, department } = await searchParams;

  let all: Awaited<ReturnType<typeof getVacancies>>;
  let filtered: Awaited<ReturnType<typeof getVacancies>>;
  try {
    // The unfiltered set populates the filter options, so a filter that matches
    // nothing still offers the full choice back.
    [all, filtered] = await Promise.all([
      getVacancies(),
      getVacancies({ ...(office ? { office } : {}), ...(department ? { department } : {}) }),
    ]);
  } catch {
    return (
      <>
        <h1>Careers</h1>
        <ErrorState retry={<RetryButton label="Try again" />}>
          <p>We could not load our open roles.</p>
        </ErrorState>
      </>
    );
  }

  const offices = [...new Set(all.map((v) => v.office_city))].sort();
  const departments = [...new Set(all.map((v) => v.department))].sort();
  const isFiltered = Boolean(office || department);

  return (
    <>
      <h1>Careers</h1>
      <p className="eaios-hero__lede">
        We hire people who want to own the systems they build, and stay with them
        afterwards.
      </p>

      {all.length > 0 ? (
        <VacancyFilters
          offices={offices}
          departments={departments}
          selected={{ office, department }}
        />
      ) : null}

      <section className="eaios-section" aria-labelledby="roles">
        <h2 id="roles">
          {isFiltered ? `Matching roles (${filtered.length})` : `Open roles (${filtered.length})`}
        </h2>

        {filtered.length === 0 ? (
          <EmptyState
            title={isFiltered ? "No roles match that filter" : "No open roles right now"}
            action={
              isFiltered ? (
                <a href="/careers" className="eaios-button eaios-button--secondary">
                  Clear filters
                </a>
              ) : (
                <Link href="/contact" className="eaios-button eaios-button--secondary">
                  Get in touch
                </Link>
              )
            }
          >
            <p>
              {isFiltered
                ? "Try a different office or team — we may be hiring elsewhere."
                : "We are not hiring at the moment, but we are always glad to hear from good people."}
            </p>
          </EmptyState>
        ) : (
          <div className="eaios-grid">
            {filtered.map((vacancy) => (
              <Card key={vacancy.slug} title={vacancy.title}>
                <p>
                  <Tag>{vacancy.department}</Tag>{" "}
                  <Tag>
                    {vacancy.office_city}, {vacancy.office_country}
                  </Tag>
                </p>
                <p>
                  Posted <time dateTime={vacancy.posted_on}>{vacancy.posted_on}</time>
                </p>
                <Link href={`/careers/${vacancy.slug}`}>See the role</Link>
              </Card>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
