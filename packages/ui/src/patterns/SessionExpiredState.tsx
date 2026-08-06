import type { ReactNode } from "react";

/**
 * The session ended while the person was still here (spec 003 FR-005, FR-029).
 *
 * Held distinct from the unauthenticated state on purpose, and the specification's
 * edge case says why: "the interface must say the session expired rather than showing
 * a generic failure". Those are two different sentences to two different people — one
 * has never signed in, the other was working a moment ago and has just lost their
 * place. Collapsing them tells the second person nothing about what happened, and a
 * portal that goes blank after a thirty-minute pause reads as broken rather than as
 * secure.
 *
 * `role="status"` rather than `alert`: this is an expected consequence of a rule the
 * user was never told about, not an error they caused. It is announced, but it does
 * not interrupt.
 *
 * No prop carries a reason. Whether the idle bound or the absolute cap ended the
 * session is in the audit trail, and telling the caller which one fired is internal
 * detail FR-022 keeps out of responses — the same reasoning applies to a page.
 */
export function SessionExpiredState({
  title = "Your session has ended",
  children,
  action,
}: {
  title?: string;
  children?: ReactNode;
  /** The way back in. Rendered by the caller so this stays free of routing. */
  action?: ReactNode;
}) {
  return (
    <div className="eaios-state eaios-state--expired" role="status">
      <p className="eaios-state__title">{title}</p>
      <div>
        {children ?? (
          <p>
            You have been signed out to keep your account safe. Sign in again to carry
            on — nothing you were looking at has changed.
          </p>
        )}
      </div>
      {action ? <div className="eaios-actions">{action}</div> : null}
    </div>
  );
}
