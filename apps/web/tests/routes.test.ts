/**
 * One route inventory, read by everything that claims to cover "every page"
 * (spec 002 FR-001, FR-001a, FR-003, FR-042).
 *
 * The same eight paths were written out three times: `lib/navigation.ts` for the
 * header and footer, `app/sitemap.ts` for crawlers, and `e2e/pages.ts` for the
 * metadata, accessibility, responsive, state-coverage, and performance sweeps.
 * Nothing compared them. A page added to two of the three would be either
 * unreachable, unindexed, or unchecked — and each of those failures is silent.
 *
 * `lib/pages.ts` is now the single declaration. `NAV_LINKS` keeps its own shape
 * because it carries labels as well as addresses, so this file is what stops it
 * drifting.
 */

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { NAV_LINKS } from "../lib/navigation";
import { NON_CONTENT_ROUTES, PUBLIC_PAGES } from "../lib/pages";

describe("the navigation covers exactly the public pages", () => {
  it("links to every page and to no others", () => {
    // Both directions, deliberately. A subset would leave a page unreachable
    // (FR-003); a superset would put a link in the header that goes nowhere.
    expect(NAV_LINKS.map((link) => link.href).sort()).toEqual([...PUBLIC_PAGES].sort());
  });

  it("gives every link a label", () => {
    for (const link of NAV_LINKS) {
      expect(link.label.trim().length).toBeGreaterThan(0);
    }
  });

  it("never links to a non-content route", () => {
    // FR-001a — `/portal` is reached through the portal control, not the page nav,
    // and `/status` is a diagnostic route.
    const hrefs = new Set(NAV_LINKS.map((link) => link.href));
    for (const route of NON_CONTENT_ROUTES) {
      expect(hrefs.has(route as (typeof NAV_LINKS)[number]["href"])).toBe(false);
    }
  });
});

describe("the shared list is real", () => {
  it("names the pages FR-001 requires", () => {
    // Guards every assertion above from passing on an empty or truncated list.
    expect(PUBLIC_PAGES).toHaveLength(8);
    expect(PUBLIC_PAGES).toContain("/");
    expect(PUBLIC_PAGES).toContain("/contact");
  });

  it("keeps the two sets disjoint", () => {
    const pages = new Set<string>(PUBLIC_PAGES);
    for (const route of NON_CONTENT_ROUTES) expect(pages.has(route)).toBe(false);
  });
});

describe("no page is frozen at build time (FR-006b, plan R7)", () => {
  /**
   * The behavioural proof lives in `tests/integration/test_request_time_rendering.py`,
   * which writes to the database and reads the site back. This is its cheap
   * companion: it runs in the `web` CI job, which has no stack, and it catches the
   * specific opt-ins that would reintroduce build-time staleness.
   *
   * Those opt-ins are what matter here rather than `cache: "no-store"` itself. Next
   * 15 already defaults `fetch` to no-store, so the presence of that option is not
   * what keeps the site fresh — a route segment declaring `revalidate` or
   * `dynamic = "force-static"` is what would override it, silently, in a file nobody
   * would think to look at.
   */
  const app = resolve(dirname(fileURLToPath(new URL(import.meta.url))), "../app");

  const pageSources = (): { file: string; source: string }[] => {
    const found: { file: string; source: string }[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const child = join(dir, entry.name);
        if (entry.isDirectory()) walk(child);
        else if (/^(page|layout)\.tsx$/.test(entry.name))
          found.push({ file: child, source: readFileSync(child, "utf-8") });
      }
    };
    walk(app);
    return found;
  };

  it("declares no revalidation window", () => {
    const offenders = pageSources()
      .filter(({ source }) => /export\s+const\s+revalidate/.test(source))
      .map(({ file }) => file);
    expect(offenders, "a revalidate window makes a reseed invisible until it lapses").toEqual([]);
  });

  it("forces no page to be static", () => {
    const offenders = pageSources()
      .filter(({ source }) => /dynamic\s*=\s*["']force-static["']/.test(source))
      .map(({ file }) => file);
    expect(offenders).toEqual([]);
  });

  it("the scan reads every page in the app", () => {
    // Guards both assertions above from passing on an empty file list — the failure
    // this whole area exists to prevent.
    const files = pageSources().map(({ file }) => file);
    expect(files.length).toBeGreaterThanOrEqual(PUBLIC_PAGES.length);
    expect(files.some((file) => file.endsWith(join("app", "page.tsx")))).toBe(true);
  });
});

describe("colour comes from the token layer (research R4, FR-031)", () => {
  /**
   * R4's implementation amendment names the property the styling decision actually
   * wanted: "no hard-coded colour or spacing outside the token layer". Nothing
   * enforced it, and it was already broken — `app/status/StatusPage.tsx` rendered
   * `border: "1px solid #b00"` and `borderBottom: "1px solid #ddd"` inline, while
   * `tokens.css` had `--danger` and `--border` defined for exactly those.
   *
   * The cost is not tidiness. FR-035 makes contrast checkable *at the palette
   * level*; a colour written inline has never been through that check, and axe only
   * sees the pages it sweeps in the states it finds them in.
   *
   * Scoped to hex literals in source. `tokens.css` is the one file allowed to hold
   * them — that is what being the token layer means.
   */
  const app = resolve(dirname(fileURLToPath(new URL(import.meta.url))), "..");

  const sources = (dir: string): { file: string; source: string }[] => {
    const found: { file: string; source: string }[] = [];
    const walk = (current: string) => {
      for (const entry of readdirSync(current, { withFileTypes: true })) {
        const child = join(current, entry.name);
        if (entry.isDirectory()) walk(child);
        else if (/\.(tsx|ts|css)$/.test(entry.name) && entry.name !== "tokens.css")
          found.push({ file: child, source: readFileSync(child, "utf-8") });
      }
    };
    walk(join(app, dir));
    return found;
  };

  /** `#fff`, `#0b5c8a`, `#0b5c8aff` — but not `#home-services` or a slug fragment. */
  const HEX = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b(?![\w-])/g;

  it("no hex colour appears outside the token layer", () => {
    const offenders: string[] = [];
    for (const dir of ["app", "components"]) {
      for (const { file, source } of sources(dir)) {
        for (const match of source.match(HEX) ?? []) {
          offenders.push(`${file.slice(app.length + 1)}: ${match}`);
        }
      }
    }
    expect(offenders, "use a token from packages/ui/src/tokens.css instead").toEqual([]);
  });

  it("the scan reads real files", () => {
    // Without this, a wrong path returns no files and the assertion above passes
    // for the worst possible reason.
    const files = [...sources("app"), ...sources("components")];
    expect(files.length).toBeGreaterThan(10);
    expect(files.some(({ file }) => file.endsWith("StatusPage.tsx"))).toBe(true);
  });

  it("the scan recognises a hex colour when it sees one", () => {
    // The regex is the whole check; a pattern that matched nothing would be
    // indistinguishable from a clean codebase.
    expect('style={{ color: "#b00" }}'.match(HEX)).toEqual(["#b00"]);
    expect('borderBottom: "1px solid #ddd"'.match(HEX)).toEqual(["#ddd"]);
    expect('href="/news/a-release-abc123"'.match(HEX)).toBeNull();
  });
});
