import Link from "next/link";
import type { ReactNode } from "react";

import { EmptyState, ErrorState } from "@eaios/ui";

import { RetryButton } from "./RetryButton";

/**
 * Renders one server-rendered content region in whichever state applies.
 *
 * FR-025, as amended in the checklist-remediation session, requires *populated*,
 * *empty*, and *error* for a server-rendered region — there is no loading state,
 * because content arrives with the document.
 *
 * FR-030 is the reason this is per-region rather than per-page: one failing section
 * must not replace the whole page. A visitor who came for the office addresses
 * should still get them when the news feed is down.
 */
export async function Section<T>({
  title,
  id,
  load,
  empty,
  more,
  children,
}: {
  title: string;
  id: string;
  load: () => Promise<T[]>;
  empty: { title: string; body: string };
  /**
   * FR-005 — a summary block must offer the way onward to its full page. Optional
   * because a region that *is* the full page has nowhere further to go; the home
   * page passes it, the listing pages do not.
   *
   * Rendered only alongside content. Offering "see all twelve" under an empty state
   * that just said there are none reads as a contradiction, and the empty state
   * already carries its own next action (FR-026).
   */
  more?: { href: string; label: string };
  children: (items: T[]) => ReactNode;
}) {
  let items: T[];
  try {
    items = await load();
  } catch {
    // Deliberately swallows the cause. FR-027 forbids exposing internal failure
    // detail, and passing the message through to a prop is how it escapes.
    return (
      <section className="eaios-section" aria-labelledby={id}>
        <h2 id={id}>{title}</h2>
        <ErrorState retry={<RetryButton />}>
          <p>This section could not be loaded.</p>
        </ErrorState>
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="eaios-section" aria-labelledby={id}>
        <h2 id={id}>{title}</h2>
        <EmptyState
          title={empty.title}
          // A link styled as a button, not a button wrapping a link: nesting an
          // anchor inside a button is invalid markup and hands assistive
          // technology two conflicting controls.
          action={
            <Link href="/contact" className="eaios-button eaios-button--secondary">
              Get in touch
            </Link>
          }
        >
          <p>{empty.body}</p>
        </EmptyState>
      </section>
    );
  }

  return (
    <section className="eaios-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="eaios-grid">{children(items)}</div>
      {more ? (
        <div className="eaios-actions">
          <Link href={more.href} className="eaios-button eaios-button--secondary">
            {more.label}
          </Link>
        </div>
      ) : null}
    </section>
  );
}
