import type { ReactNode } from "react";

/**
 * A designed refusal (spec 003 FR-029; Constitution, Frontend completeness).
 *
 * The constitution is unusually specific here: access-denied "MUST be a designed,
 * informative state — never a blank screen, a silent omission, or a raw 403". All
 * three of those are what you get by default, which is why this component exists
 * rather than a `catch` that renders nothing.
 *
 * **It accepts no reason, and that is deliberate.** FR-022 forbids a refusal
 * disclosing internal detail — no reason code, no indication of which rule fired, no
 * hint about what would have been permitted. "You do not have access to this" is the
 * complete, honest answer available to the person reading it. The full reason exists,
 * with the layer that decided and the actor who asked, in the audit trail where an
 * auditor can read it and a caller cannot.
 *
 * `role="alert"`: unlike an expired session, this *is* a dead end for this person on
 * this page, and it should interrupt rather than wait to be noticed.
 */
export function AccessDeniedState({
  title = "You do not have access to this",
  children,
  action,
}: {
  title?: string;
  children?: ReactNode;
  /** Somewhere to go instead. A refusal with no way onward is a trap. */
  action?: ReactNode;
}) {
  return (
    <div className="eaios-state eaios-state--denied" role="alert">
      <p className="eaios-state__title">{title}</p>
      <div>
        {children ?? (
          <p>
            Your account does not have permission for this area. If you think it
            should, your manager or the IT team can arrange it.
          </p>
        )}
      </div>
      {action ? <div className="eaios-actions">{action}</div> : null}
    </div>
  );
}
