import type { Metadata } from "next";
import Link from "next/link";

import { AccessDeniedState, EmptyState, ErrorState } from "@eaios/ui";

import { NOT_INDEXED } from "../../../../lib/metadata";
import { type DirectReport, ForbiddenError, getDirectReports } from "../../../../lib/portal-api";

export const metadata: Metadata = {
  title: "My team",
  description: "The people who report to you.",
  ...NOT_INDEXED,
};

/**
 * A manager's direct reports (spec 003 FR-024, US2).
 *
 * **Empty and denied are different pages, and this is where the difference shows.**
 * A permitted caller with nobody reporting to them gets the empty state — "you have no
 * direct reports" is a fact about the org chart. A caller without `hr:read_team` gets
 * the access-denied state — "you may not see this" is a fact about permissions.
 * Collapsing them would tell a manager with a vacant team that they lack access, and
 * tell an employee without the permission that their team is empty. Both are wrong,
 * and each is wrong in a way that sends the person to the wrong place for help.
 *
 * The list is thin — name, title, department. Every profile it links to is fetched by
 * its own authorized request, so this page cannot become a way to read profile content
 * in bulk without a per-record decision.
 */
export default async function TeamPage() {
  let reports: DirectReport[];
  try {
    reports = await getDirectReports();
  } catch (error) {
    if (error instanceof ForbiddenError) {
      return (
        <AccessDeniedState title="You do not manage a team">
          <p>
            This area is for people with direct reports. If you have recently become a
            manager, your HR team can update your record.
          </p>
        </AccessDeniedState>
      );
    }
    return (
      <ErrorState title="Your team could not be loaded">
        <p>Something went wrong on our side. Please try again in a moment.</p>
        <p>
          <Link href="/portal/team">Try again</Link>
        </p>
      </ErrorState>
    );
  }

  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>My team</h1>

      {reports.length === 0 ? (
        <EmptyState
          title="Nobody reports to you at the moment"
          action={
            <Link href="/portal/home" className="eaios-button">
              Back to the portal
            </Link>
          }
        >
          <p>
            When someone is assigned to you, they will appear here and you will be able
            to see their HR profile.
          </p>
        </EmptyState>
      ) : (
        <ul className="eaios-team-list">
          {reports.map((person) => (
            <li key={person.user_id}>
              <Link href={`/portal/team/${person.user_id}`}>{person.full_name}</Link>
              <span className="eaios-team-list__meta">
                {person.job_title} · {person.department}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
