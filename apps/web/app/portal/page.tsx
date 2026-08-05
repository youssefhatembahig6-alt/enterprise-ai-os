import type { Metadata } from "next";
import Link from "next/link";

import { Alert } from "@eaios/ui";

import { NOT_INDEXED } from "../../lib/metadata";

/**
 * The reserved employee-portal address (spec 002 FR-049a).
 *
 * The route exists now, before the portal does, so the anonymous boundary in
 * FR-046 is enforced and tested rather than arriving with the feature it guards.
 * When the portal is built it replaces this page's contents **without changing the
 * address**, so the link in every header keeps working.
 *
 * Three things it must not do, each asserted by
 * `tests/security/test_anonymous_refusal.py` or the e2e boundary spec:
 * present a credential field (FR-048 — this site accepts no credentials), return a
 * raw error or blank screen, or reveal any portal structure beyond its existence.
 */
export const metadata: Metadata = {
  title: "Employee portal",
  description: "Sign-in for NileTech employees.",
  ...NOT_INDEXED,
};

export default function PortalPage() {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>Employee portal</h1>

      <Alert tone="success" title="Sign-in is not yet available">
        <p>
          The employee portal is still being built. When it opens, this is where you will
          sign in — the address will not change.
        </p>
      </Alert>

      <p>
        If you need something in the meantime, your usual contact inside NileTech is the
        fastest route.
      </p>

      <div className="eaios-actions">
        <Link href="/" className="eaios-button">
          Back to the public site
        </Link>
        <Link href="/contact" className="eaios-button eaios-button--secondary">
          Contact us
        </Link>
      </div>
    </div>
  );
}
