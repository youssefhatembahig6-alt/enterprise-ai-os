import Link from "next/link";

import type { CurrentUser } from "../../lib/portal-api";

/**
 * Role-aware navigation (spec 003 FR-028, SC-008; Constitution: Mandatory Surfaces).
 *
 * The constitution states it plainly: "a user never sees an entry point to something
 * they cannot use." An entry the caller lacks the permission for is **not rendered at
 * all** — not disabled, not hidden with CSS. `display: none` is still in the DOM, still
 * in the accessibility tree on some readings, and still findable by anyone who opens
 * the page source; "absent from the markup" is the only version of hidden that is
 * actually hidden.
 *
 * **Permission codes, never role names** (FR-014). A check written against "Manager"
 * produces the right answer today and the wrong one the moment a tenant administrator
 * recomposes what Manager means.
 *
 * **Hiding is presentation, and only presentation.** The server refuses these
 * addresses regardless of what was rendered — `tests/security/test_manager_scope.py`
 * requests every hidden address directly and asserts the refusal. If this component
 * were the only control, it would be no control at all.
 */

type Entry = {
  href: string;
  label: string;
  /** Null means every signed-in user may see it. */
  permission: string | null;
};

/**
 * The portal's areas, in the order they appear.
 *
 * Only what exists. The constitution's full portal list names an AI Assistant,
 * Documents, Reports, and more — those arrive in feature 004, and rendering a link to
 * a page that does nothing would violate this component's own rule: an entry point to
 * something the user cannot use.
 */
export const PORTAL_ENTRIES: readonly Entry[] = [
  { href: "/portal/home", label: "Home", permission: null },
  { href: "/portal/profile", label: "My HR profile", permission: "hr:read_self" },
  { href: "/portal/team", label: "My team", permission: "hr:read_team" },
] as const;

export function visibleEntries(user: CurrentUser): Entry[] {
  return PORTAL_ENTRIES.filter(
    (entry) => entry.permission === null || user.permissions.includes(entry.permission),
  );
}

export function PortalNav({ user }: { user: CurrentUser }) {
  const entries = visibleEntries(user);

  return (
    <nav aria-label="Portal" className="eaios-portal-nav">
      <ul>
        {entries.map((entry) => (
          <li key={entry.href}>
            <Link href={entry.href}>{entry.label}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
