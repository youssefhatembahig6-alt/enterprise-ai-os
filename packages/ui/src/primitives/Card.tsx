import type { ReactNode } from "react";

type Props = {
  title?: ReactNode;
  /** Heading level, so a card inside a section does not break heading order
   *  (FR-034). Defaults to h3, which is correct under a section's h2. */
  headingLevel?: 2 | 3 | 4;
  children: ReactNode;
};

export function Card({ title, headingLevel = 3, children }: Props) {
  const Heading = `h${headingLevel}` as const;
  return (
    <article className="eaios-card">
      {title ? <Heading className="eaios-card__title">{title}</Heading> : null}
      {children}
    </article>
  );
}
