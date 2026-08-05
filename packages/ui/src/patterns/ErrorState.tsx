import type { ReactNode } from "react";

/**
 * FR-027 — explains that content could not be loaded and offers a *manual* retry.
 *
 * No internal failure detail is accepted as a prop, so a caller cannot pass a
 * server message through to a visitor. Retry is visitor-initiated rather than
 * automatic, so a failing dependency is not amplified by the site.
 */
export function ErrorState({
  title = "This section could not be loaded",
  children,
  retry,
}: {
  title?: string;
  children?: ReactNode;
  retry?: ReactNode;
}) {
  return (
    <div className="eaios-state eaios-state--error" role="alert">
      <p className="eaios-state__title">{title}</p>
      <div>{children ?? <p>Something went wrong on our side. Please try again.</p>}</div>
      {retry ? <div className="eaios-actions">{retry}</div> : null}
    </div>
  );
}
