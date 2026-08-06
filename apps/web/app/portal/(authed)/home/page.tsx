import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@eaios/ui";

import { visibleEntries } from "../../../../components/portal/PortalNav";
import { NOT_INDEXED } from "../../../../lib/metadata";
import { getCurrentUser } from "../../../../lib/portal-api";

export const metadata: Metadata = {
  title: "Portal",
  description: "The NileTech employee portal.",
  ...NOT_INDEXED,
};

/**
 * Where a signed-in person lands (spec 003 US1, SC-001).
 *
 * SC-001 wants the employee's own record within three interactions of arriving at the
 * portal address: sign in, land here, open the profile. So this page greets them and
 * gets out of the way — every area they can reach is one click from here.
 *
 * The empty state covers the specification's edge case of "a user with no roles at
 * all": they must still sign in, reach their own record, and see a portal that
 * *explains the absence* rather than an empty page. A person whose account is
 * misconfigured should be able to tell that from the screen.
 */
export default async function PortalHome() {
  const user = await getCurrentUser();
  const areas = visibleEntries(user).filter((entry) => entry.href !== "/portal/home");

  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>Welcome, {user.full_name.split(" ")[0]}</h1>

      <p>
        {user.department} · {user.office}
      </p>

      {areas.length > 0 ? (
        <>
          <h2>Where you can go</h2>
          <ul>
            {areas.map((area) => (
              <li key={area.href}>
                <Link href={area.href}>{area.label}</Link>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <EmptyState
          title="Nothing is available to you yet"
          action={
            <Link href="/contact" className="eaios-button">
              Ask for access
            </Link>
          }
        >
          <p>
            Your account is signed in but has not been given access to any area of the
            portal. Your manager or the IT team can arrange it.
          </p>
        </EmptyState>
      )}
    </div>
  );
}
