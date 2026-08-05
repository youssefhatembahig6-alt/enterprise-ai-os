import Link from "next/link";

import { getCompany, getOffices } from "../lib/api";
import { NAV_LINKS } from "../lib/navigation";

/**
 * FR-002 — office locations, a general enquiry address, and secondary navigation.
 *
 * Reads live data like every other surface (FR-006). If the API is unreachable the
 * footer degrades to its navigation rather than taking the page down with it: a
 * failed footer is not a reason to deny someone the content they came for (FR-030).
 */
export async function SiteFooter() {
  let offices: Awaited<ReturnType<typeof getOffices>> = [];
  let domain: string | null = null;

  try {
    [offices, { domain }] = await Promise.all([
      getOffices(),
      getCompany().then((company) => ({ domain: company.domain })),
    ]);
  } catch {
    // Degrade quietly — see the note above.
  }

  return (
    <footer className="eaios-footer">
      <div className="eaios-container eaios-footer__grid">
        <div>
          <h2>NileTech Solutions</h2>
          <p>Software and business automation across Egypt and the UAE.</p>
        </div>

        <div>
          <h2>Offices</h2>
          <ul>
            {offices.map((office) => (
              <li key={`${office.city}-${office.country}`}>
                {office.city}, {office.country}
                {office.is_headquarters ? " (HQ)" : ""}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2>Contact</h2>
          <ul>
            {domain ? (
              <li>
                <a href={`mailto:hello@${domain}`}>hello@{domain}</a>
              </li>
            ) : null}
            <li>
              <Link href="/contact">Send an enquiry</Link>
            </li>
          </ul>
        </div>

        <div>
          <h2>Explore</h2>
          <ul>
            {NAV_LINKS.filter((link) => link.href !== "/").map((link) => (
              <li key={link.href}>
                <Link href={link.href}>{link.label}</Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
