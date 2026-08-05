import type { ReactNode } from "react";

/**
 * FR-026 — an empty state explains what is absent and offers a next action. It is
 * never an unexplained blank region, which a visitor reads as breakage.
 *
 * `action` is required rather than optional: an empty state with no way forward is
 * the blank region the requirement exists to prevent.
 */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action: ReactNode;
}) {
  return (
    <div className="eaios-state" role="status">
      <p className="eaios-state__title">{title}</p>
      <div>{children}</div>
      <div className="eaios-actions" style={{ justifyContent: "center" }}>
        {action}
      </div>
    </div>
  );
}
