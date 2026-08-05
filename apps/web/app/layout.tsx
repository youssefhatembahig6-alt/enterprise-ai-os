import type { Metadata } from "next";

import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { siteUrl } from "../lib/config";

import "./globals.css";

/**
 * Root layout for the public site (spec 002 FR-002).
 *
 * The title template gives every page a distinct title without each one repeating
 * the company name, which is what FR-039 forbids sharing generically. `metadataBase`
 * makes the canonical and social URLs absolute (FR-042).
 */
export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: {
    // `absolute` on the home page avoids "… — NileTech Solutions — NileTech
    // Solutions"; every other page uses the template.
    default: "NileTech Solutions — Software and business automation",
    template: "%s — NileTech Solutions",
  },
  description:
    "NileTech Solutions builds and runs business automation for enterprises in Cairo, Alexandria, and Dubai.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* First focusable element on every page. Without it, a keyboard user
            traverses the whole navigation before reaching content on each
            navigation (checklists/accessibility.md CHK001). */}
        <a className="skip-link" href="#main">
          Skip to content
        </a>

        <div className="eaios-shell">
          <SiteHeader />
          <main id="main" className="eaios-main">
            <div className="eaios-container">{children}</div>
          </main>
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
