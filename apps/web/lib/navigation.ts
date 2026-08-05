/**
 * The public content pages, in the order FR-003 presents them.
 *
 * Deliberately in its own module rather than beside the `Navigation` component.
 * That component is a client component, and a server component importing from a
 * `"use client"` module receives a client reference proxy rather than the value —
 * so `SiteFooter` got a proxy where it expected an array and the build failed at
 * prerender with `NAV_LINKS.filter is not a function`.
 */
export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/services", label: "Services" },
  { href: "/products", label: "Products" },
  { href: "/leadership", label: "Leadership" },
  { href: "/careers", label: "Careers" },
  { href: "/news", label: "News" },
  { href: "/contact", label: "Contact" },
] as const;
