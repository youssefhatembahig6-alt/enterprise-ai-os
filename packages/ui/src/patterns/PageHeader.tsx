import type { ReactNode } from "react";

/** One h1 per page (FR-034), with an optional lede beneath it. */
export function PageHeader({ title, lede }: { title: string; lede?: ReactNode }) {
  return (
    <header className="eaios-section">
      <h1>{title}</h1>
      {lede ? <p className="eaios-hero__lede">{lede}</p> : null}
    </header>
  );
}
