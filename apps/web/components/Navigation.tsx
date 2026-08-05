"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { NAV_LINKS } from "../lib/navigation";


/**
 * Primary navigation (FR-003, FR-033, FR-037).
 *
 * Three behaviours are load-bearing rather than decorative:
 *
 * * The current page is marked with `aria-current="page"`, and the styling keys off
 *   that attribute — so the visual indicator and the announced one cannot drift.
 * * The mobile menu is dismissible by Escape and returns focus to the toggle, which
 *   is what FR-037 means by trapping focus "only while open".
 * * It collapses at 767px, matching the tablet width FR-032 verifies.
 */
export function Navigation() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);

  // Close on navigation, or the menu stays open over the page just opened.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      // Focus goes back where it came from. Without this, dismissing the menu
      // leaves focus on a hidden element and the next Tab starts from the top.
      toggleRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <>
      <button
        ref={toggleRef}
        type="button"
        className="eaios-nav__toggle"
        aria-expanded={open}
        aria-controls="primary-navigation"
        onClick={() => setOpen((value) => !value)}
      >
        {/* The label stays "Menu" whether open or closed; `aria-expanded` conveys
            the state. A label that flips to "Close" would change the button's
            accessible name mid-interaction, which is both harder to script
            against and a WCAG 2.5.3 label-in-name hazard if an aria-label were
            added to stabilise it. */}
        Menu
      </button>

      <nav id="primary-navigation" className="eaios-nav" data-open={open} aria-label="Primary">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="eaios-nav__link"
            aria-current={isCurrent(link.href) ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
