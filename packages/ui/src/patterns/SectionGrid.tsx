import type { ReactNode } from "react";

/**
 * A titled section holding a responsive grid.
 *
 * The grid uses `auto-fit` with a `min(100%, 280px)` track, so it reflows at every
 * width rather than at three breakpoints — FR-032 verifies three widths but
 * requires the layout to work at all of them.
 */
export function SectionGrid({
  title,
  id,
  children,
}: {
  title: string;
  id: string;
  children: ReactNode;
}) {
  return (
    <section className="eaios-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="eaios-grid">{children}</div>
    </section>
  );
}
