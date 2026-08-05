import Link from "next/link";

import { NOT_INDEXED } from "../lib/metadata";

/**
 * FR-028, FR-043 — explains that the address does not exist and offers a way back.
 *
 * Next serves this with a 404 status, so a crawler is told the address is not
 * valid rather than indexing an apparently-fine page (FR-043).
 */
export const metadata = { title: "Page not found", ...NOT_INDEXED };

export default function NotFound() {
  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>We could not find that page</h1>
      <p>
        The address you followed does not exist, or the content behind it has moved. It
        may have been a link from somewhere out of date.
      </p>
      <div className="eaios-actions">
        <Link href="/" className="eaios-button">
          Go to the home page
        </Link>
        <Link href="/careers" className="eaios-button eaios-button--secondary">
          Browse open roles
        </Link>
        <Link href="/news" className="eaios-button eaios-button--secondary">
          Read our news
        </Link>
      </div>
    </div>
  );
}
