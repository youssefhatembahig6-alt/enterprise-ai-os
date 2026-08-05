import Link from "next/link";

import { Navigation } from "./Navigation";

/**
 * FR-002 — company identity, primary navigation, and the portal entry control.
 *
 * The portal link's accessible name says where it goes rather than just "Login",
 * because a screen-reader user reaching it out of context gets no other clue
 * (checklists/accessibility.md CHK005).
 */
export function SiteHeader() {
  return (
    <header className="eaios-header">
      <div className="eaios-container eaios-header__inner">
        <div className="eaios-header__bar">
          <Link href="/" className="eaios-brand">
            NileTech Solutions
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Navigation />
            <Link
              href="/portal"
              className="eaios-button eaios-button--secondary"
              aria-label="Sign in to the employee portal"
            >
              Employee portal
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
