import type { Metadata } from "next";
import Link from "next/link";

import { AccessDeniedState, EmptyState, ErrorState, Text } from "@eaios/ui";

import { NOT_INDEXED } from "../../../../lib/metadata";
import { ForbiddenError, getOwnProfile, type HrProfile } from "../../../../lib/portal-api";

export const metadata: Metadata = {
  title: "My HR profile",
  description: "Your own HR record.",
  ...NOT_INDEXED,
};

/**
 * The vertical slice's visible end (spec 003 FR-023, US1).
 *
 * Everything on this page is the employee's **own** record, which is why it writes no
 * audit entry: reading your own non-compensation profile is outside FR-017a's
 * sensitive set, deliberately, so one page view does not write a row.
 *
 * **No compensation appears, and not because it was filtered here.** Salary lives
 * behind its own endpoint requiring `hr:read_all`, so a request for this page never
 * executes a statement mentioning `salary_amount` at all. A page that fetched the
 * figure and declined to render it would satisfy the eye and fail the requirement.
 */
export default async function OwnProfilePage() {
  let profile: HrProfile;
  try {
    profile = await getOwnProfile();
  } catch (error) {
    if (error instanceof ForbiddenError) {
      return (
        <AccessDeniedState title="You cannot view your own HR profile">
          <p>
            Your account has not been given the permission this page needs. Your
            manager or the IT team can arrange it.
          </p>
        </AccessDeniedState>
      );
    }
    // Anything else — a store down, a timeout — is a failure on our side, and says so
    // without a status code, a hostname, or a stack trace (FR-022).
    return (
      <ErrorState title="Your profile could not be loaded">
        <p>Something went wrong on our side. Please try again in a moment.</p>
        <p>
          <Link href="/portal/profile">Try again</Link>
        </p>
      </ErrorState>
    );
  }

  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>My HR profile</h1>

      <dl className="eaios-detail-list">
        <dt>Name</dt>
        <dd>
          <Text value={profile.full_name} fallback="Not recorded" />
        </dd>

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

        <dt>Manager</dt>
        <dd>
          {/* Null for exactly one person per company — the top-level executive. That
              is a fact about the org chart, not missing data, so it gets a sentence
              rather than a dash. */}
          <Text value={profile.manager_name ?? ""} fallback="No manager — you report to nobody" />
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

      <h2>Annual leave</h2>
      {profile.leave_balance ? (
        <dl className="eaios-detail-list">
          <dt>Entitlement</dt>
          <dd>{profile.leave_balance.entitlement_days} days</dd>
          <dt>Taken</dt>
          <dd>{profile.leave_balance.used_days} days</dd>
          <dt>Remaining</dt>
          <dd>
            <strong>{profile.leave_balance.remaining_days} days</strong>
          </dd>
        </dl>
      ) : (
        // "No balance recorded" and "zero days left" are different facts, and showing
        // a zero for the first would be a lie with consequences.
        <EmptyState
          title="No leave balance recorded"
          action={
            <Link href="/contact" className="eaios-button">
              Ask HR about this
            </Link>
          }
        >
          <p>
            We do not have an annual leave balance for you this year yet. This is
            usually a record that has not been set up rather than a balance of zero.
          </p>
        </EmptyState>
      )}
    </div>
  );
}
