import type { Metadata } from "next";
import Link from "next/link";

import { AccessDeniedState } from "@eaios/ui";

import { NOT_INDEXED } from "../../../../lib/metadata";

export const metadata: Metadata = {
  title: "No access",
  description: "You do not have access to this area.",
  ...NOT_INDEXED,
};

/**
 * The standalone access-denied page (spec 003 FR-029, US4 acceptance scenario 3).
 *
 * "Given a user who reaches a forbidden address directly, when the page renders, then
 * they see a designed access-denied state explaining that they lack access — never a
 * blank screen or a raw error."
 *
 * Each page renders its own denial inline where it can, because a refusal in context
 * is more use than one on a separate screen — you can still see where you were. This
 * page is for the case where there is no context: a bookmarked area that has since
 * been withdrawn, or a link somebody was sent who was never meant to have it.
 *
 * It states no reason. FR-022 forbids a refusal disclosing internal detail, and "which
 * permission you are missing" is exactly that — it tells someone probing the portal
 * what to ask for. The real reason is in the audit trail with the actor, the resource,
 * and the rule that fired.
 */
export default function PortalDeniedPage() {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>No access</h1>

      <AccessDeniedState>
        <p>
          Your account does not have permission for this area of the portal. If you
          believe it should, your manager or the IT team can arrange it.
        </p>
      </AccessDeniedState>

      <div className="eaios-actions">
        <Link href="/portal/home" className="eaios-button">
          Back to the portal
        </Link>
      </div>
    </div>
  );
}
