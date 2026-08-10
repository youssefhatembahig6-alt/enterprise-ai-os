import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AccessDeniedState, ErrorState, Text } from "@eaios/ui";

import { NOT_INDEXED } from "../../../../../lib/metadata";
import {
  ForbiddenError,
  getProfile,
  type HrProfile,
  PortalNotFoundError,
} from "../../../../../lib/portal-api";

export const metadata: Metadata = {
  title: "Team member",
  description: "A direct report's HR profile.",
  ...NOT_INDEXED,
};

type Props = { params: Promise<{ userId: string }> };

/**
 * One person's HR profile, reached by a manager (spec 003 FR-024, US2).
 *
 * **The same address behaves differently depending on who asks**, which is the
 * blueprint's flagship demonstration. A manager reaching a direct report sees the
 * record; the same URL for an employee outside their reporting line is refused, and
 * the same URL for somebody in another tenant is *not found*.
 *
 * Those two refusals are rendered differently on purpose. 403 says "you may not see
 * this person" — they exist, and the answer is about permission. 404 says "no such
 * person", and it is what a caller in another tenant sees, indistinguishable from an
 * identifier belonging to nobody (FR-021, FR-030). Rendering the first for the second
 * would confirm the record exists, which is exactly the enumeration the tenant
 * boundary's placement at layer 1 is designed to prevent.
 *
 * Unlike the own-profile page, this read **is** audited: an HR record belonging to
 * someone other than the requester is in FR-017a's sensitive set.
 */
export default async function TeamMemberPage({ params }: Props) {
  const { userId } = await params;

  let profile: HrProfile;
  try {
    profile = await getProfile(userId);
  } catch (error) {
    if (error instanceof PortalNotFoundError) notFound();
    if (error instanceof ForbiddenError) {
      return (
        <div style={{ maxWidth: "var(--content-narrow)" }}>
          <p>
            <Link href="/portal/team">← My team</Link>
          </p>
          <AccessDeniedState title="You cannot view this person's profile">
            <p>
              You can see the HR profiles of people who report to you directly. This
              person is not one of them.
            </p>
          </AccessDeniedState>
        </div>
      );
    }
    // The retry was missing here while the other two portal error states had one, so a
    // failure on this page was a dead end. `retry` rather than a link in the children:
    // contracts/portal-routes.md §3 names the prop, and it had gone unused since
    // feature 002.
    return (
      <ErrorState
        title="This profile could not be loaded"
        retry={<Link href={`/portal/team/${encodeURIComponent(userId)}`}>Try again</Link>}
      >
        <p>Something went wrong on our side. Please try again in a moment.</p>
      </ErrorState>
    );
  }

  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <p>
        <Link href="/portal/team">← My team</Link>
      </p>

      <h1>{profile.full_name}</h1>

      <dl className="eaios-detail-list">
        <dt>Job title</dt>
        <dd>
          <Text value={profile.job_title} fallback="Not recorded" />
        </dd>

        <dt>Department</dt>
        <dd>
          <Text value={profile.department} fallback="Not recorded" />
        </dd>

        <dt>Office</dt>
        <dd>
          <Text value={profile.office} fallback="Not recorded" />
        </dd>

        <dt>Employment type</dt>
        <dd>
          <Text value={profile.employment_type} fallback="Not recorded" />
        </dd>

        <dt>Started</dt>
        <dd>
          <time dateTime={profile.hire_date}>{profile.hire_date}</time>
        </dd>
      </dl>

      {/*
        No compensation, and no "you may not see the salary" placeholder either. FR-025
        is satisfied by the figure never being fetched — a page that showed a locked
        row would be telling the manager there is something here they are missing,
        which is a disclosure of its own.
      */}
    </div>
  );
}
