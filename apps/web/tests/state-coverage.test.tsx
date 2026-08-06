/**
 * Every content page renders its empty and error states (spec 002 FR-025, FR-026,
 * FR-027, FR-054, SC-012).
 *
 * The evidence for FR-054 was previously `Section.test.tsx` alone: the shared
 * region component was exercised in all three states, and every page that used it
 * inherited the proof. Two pages do not use it. `app/careers/page.tsx` and
 * `app/contact/page.tsx` hand-roll their own regions, so a page that implemented no
 * empty state at all was indistinguishable, to the suite, from one that did — and
 * one of them had none. The check has to run against the pages, not against the
 * component they happen to share.
 *
 * The page list is imported from `e2e/pages.ts` rather than restated here, and
 * `TestTheListIsBound` fails if the registry below drifts from it. A page added in
 * six months is covered by this file the moment it is added to that list, without
 * anyone remembering this file exists.
 *
 * **What this does not do.** It resolves the pages' server components in-process
 * with a mocked API. It does not exercise Next's routing, streaming, or caching —
 * `e2e/` does that against the real stack. What it establishes is narrower and is
 * the thing FR-054 asks for: for each page, when its sources return nothing, a
 * visitor is told so; when its sources fail, a visitor is told that instead, and is
 * told nothing about why.
 */

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render, within } from "@testing-library/react";
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PUBLIC_PAGES } from "../e2e/pages";
import * as api from "../lib/api";

vi.mock("../lib/api");

/** The rejection every failing source throws. Distinctive so FR-027's prohibition
 *  on exposing internal detail can be checked by searching for it. */
const INTERNAL_DETAIL = "psycopg.OperationalError at 10.0.3.14:5432";

const POPULATED = {
  getCompany: { name: "NileTech Solutions", domain: "niletech.example" },
  getOffices: [
    { city: "Cairo", country: "Egypt", address: "12 Nile Corniche", is_headquarters: true },
  ],
  getServices: [
    { name: "Process Automation", summary: "Summary.", description: "Detail.", display_order: 1 },
  ],
  getProducts: [
    { name: "Horus Ledger", tagline: "Tagline.", description: "Detail.", display_order: 1 },
  ],
  getLeadership: [
    { full_name: "Mariam Lotfy", public_title: "Chief Executive", bio: "Bio.", display_order: 1 },
  ],
  getNews: {
    items: [{ slug: "a-release-abc123", headline: "A release", published_on: "2026-05-01" }],
    total: 1,
  },
  getVacancies: [
    {
      slug: "engineer-abc123",
      title: "Platform Engineer",
      department: "Engineering",
      office_city: "Cairo",
      office_country: "Egypt",
      posted_on: "2026-05-01",
    },
  ],
} as const;

const EMPTY = {
  getCompany: POPULATED.getCompany, // A company always exists; its lists may not.
  getOffices: [],
  getServices: [],
  getProducts: [],
  getLeadership: [],
  getNews: { items: [], total: 0 },
  getVacancies: [],
} as const;

type SourceName = keyof typeof POPULATED;
const SOURCES = Object.keys(POPULATED) as SourceName[];

/** Every string the populated fixture carries, so "did the page render its data?"
 *  is answered against the data rather than against a character count. */
const FIXTURE_VALUES: string[] = (function collect(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(collect);
  if (value && typeof value === "object") return Object.values(value).flatMap(collect);
  return [];
})(POPULATED);

/** `EmptyState` and `ErrorState` render these; addressing them by class keeps the
 *  assertions off unrelated live regions. */
const EMPTY_STATE = '.eaios-state[role="status"]';
const ERROR_STATE = '.eaios-state[role="alert"]';

function stub(mode: "populated" | "empty" | "error"): void {
  for (const name of SOURCES) {
    const fn = vi.mocked(api)[name] as unknown as ReturnType<typeof vi.fn>;
    if (mode === "error") {
      fn.mockRejectedValue(new Error(INTERNAL_DETAIL));
    } else {
      const value = mode === "populated" ? POPULATED[name] : EMPTY[name];
      fn.mockResolvedValue(structuredClone(value));
    }
  }
}

/**
 * Resolves the async server components in a page's element tree.
 *
 * Only async components are invoked — identified by their constructor, not by
 * calling them to see what comes back. Calling a *client* component directly would
 * run its hooks outside a render and throw; `ContactForm` and `VacancyFilters` are
 * left as elements for React to render normally.
 */
const isAsyncComponent = (type: unknown): type is (props: unknown) => Promise<ReactNode> =>
  typeof type === "function" && type.constructor?.name === "AsyncFunction";

async function resolveServerTree(node: ReactNode): Promise<ReactNode> {
  if (Array.isArray(node)) return Promise.all(node.map(resolveServerTree)) as Promise<ReactNode>;
  if (!isValidElement(node)) return node;

  const element = node as ReactElement<{ children?: ReactNode }>;

  if (isAsyncComponent(element.type)) {
    return resolveServerTree(await element.type(element.props));
  }
  // Descend through fragments and host elements to reach nested regions. Sync
  // components are handed to React intact.
  if (typeof element.type !== "function" && element.props?.children !== undefined) {
    return cloneElement(element, {}, await resolveServerTree(element.props.children));
  }
  return element;
}

type PageEntry = {
  /** Path in `PUBLIC_PAGES`. Bound by `TestTheListIsBound`. */
  path: string;
  load: () => Promise<{ default: (props: never) => ReactNode | Promise<ReactNode> }>;
  props?: unknown;
};

const REGISTRY: PageEntry[] = [
  { path: "/", load: () => import("../app/page") },
  { path: "/about", load: () => import("../app/about/page") },
  { path: "/services", load: () => import("../app/services/page") },
  { path: "/products", load: () => import("../app/products/page") },
  { path: "/leadership", load: () => import("../app/leadership/page") },
  {
    path: "/careers",
    load: () => import("../app/careers/page"),
    props: { searchParams: Promise.resolve({}) },
  },
  { path: "/news", load: () => import("../app/news/page") },
  { path: "/contact", load: () => import("../app/contact/page") },
];

async function renderPage(entry: PageEntry, mode: "populated" | "empty" | "error") {
  stub(mode);
  const module = await entry.load();
  const Page = module.default as (props: unknown) => ReactNode | Promise<ReactNode>;
  // `searchParams` is a promise consumed once, so it is rebuilt per render rather
  // than reused from the registry.
  const props = entry.path === "/careers" ? { searchParams: Promise.resolve({}) } : entry.props;
  return render((await resolveServerTree(await Page(props))) as ReactElement);
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("TestTheListIsBound", () => {
  it("covers every page in the shared list, and no others", () => {
    // Both directions. Covering a subset would let a new page go unchecked; listing
    // a page that no longer exists would leave a passing assertion about nothing.
    expect(REGISTRY.map((entry) => entry.path).sort()).toEqual([...PUBLIC_PAGES].sort());
  });

  it("stubs every source the client exposes", () => {
    // If a page started reading a source absent from POPULATED/EMPTY, its mock
    // would resolve `undefined` and the page would throw — which the error-state
    // assertions would happily accept as success.
    const exported = Object.keys(api).filter(
      (key) => key.startsWith("get") && typeof (api as Record<string, unknown>)[key] === "function",
    );
    const unstubbed = exported.filter(
      (key) => !SOURCES.includes(key as SourceName) && !["getNewsItem", "getVacancy"].includes(key),
    );
    expect(unstubbed).toEqual([]);
  });
});

describe.each(REGISTRY)("$path", (entry) => {
  it("renders its content when its sources return data", async () => {
    const { container } = await renderPage(entry, "populated");
    const text = container.textContent ?? "";

    // Guards both assertions below. A page stuck permanently in its empty or error
    // state would satisfy them while showing a visitor none of the content it was
    // given — so the populated case is asserted against the fixture's own values.
    expect(FIXTURE_VALUES.some((value) => text.includes(value))).toBe(true);
    expect(container.querySelector(ERROR_STATE)).toBeNull();
    expect(container.querySelector(EMPTY_STATE)).toBeNull();
  });

  it("explains what is absent when its sources return nothing", async () => {
    const { container } = await renderPage(entry, "empty");

    // Addressed by class, not by role. A form's own live region is also
    // `role="status"` and is legitimately empty until it has something to announce;
    // matching it here would assert against the wrong element on `/contact`.
    const states = [...container.querySelectorAll(EMPTY_STATE)];
    expect(states.length, "page renders no empty state at all").toBeGreaterThan(0);

    for (const state of states) {
      // FR-026 — an explanation and a next action, not a bare heading.
      expect(state.textContent?.trim().length ?? 0).toBeGreaterThan(20);
      expect(within(state as HTMLElement).getByRole("link")).toBeInTheDocument();
    }
  });

  it("leaves no content region blank when its sources return nothing", async () => {
    const { container } = await renderPage(entry, "empty");

    for (const section of container.querySelectorAll("section")) {
      const heading = section.querySelector("h1, h2, h3");
      const body = section.textContent?.replace(heading?.textContent ?? "", "").trim() ?? "";
      expect(body, `region "${heading?.textContent}" renders nothing but its heading`).not.toBe("");
    }
  });

  it("reports failure when its sources fail", async () => {
    const { container } = await renderPage(entry, "error");
    expect(container.querySelectorAll(ERROR_STATE).length).toBeGreaterThan(0);
  });

  it("offers a manual retry from every error state", async () => {
    // FR-027 requires an error state to *offer* a retry, not to instruct the
    // visitor to perform one. `ErrorState` carried a `retry` prop that no caller
    // anywhere in the application passed, so every error state on the site read
    // "Please refresh to try again" — advice, not an affordance. This assertion is
    // what makes the next page written unable to repeat that.
    const { container } = await renderPage(entry, "error");

    for (const state of container.querySelectorAll(ERROR_STATE)) {
      const control = state.querySelector("button, a");
      expect(control, `error state "${state.textContent?.slice(0, 40)}" offers no retry`).not.toBe(
        null,
      );
    }
  });

  it("does not retry on its own", async () => {
    // The other half of FR-027, and the reason retry is a control rather than an
    // effect: a site that re-requested automatically would amplify the load on the
    // dependency that is already failing. Each source is called exactly as many
    // times as the render needs, and no more.
    stub("error");
    const before = SOURCES.reduce(
      (total, name) => total + (vi.mocked(api)[name] as ReturnType<typeof vi.fn>).mock.calls.length,
      0,
    );
    await renderPage(entry, "error");
    const after = SOURCES.reduce(
      (total, name) => total + (vi.mocked(api)[name] as ReturnType<typeof vi.fn>).mock.calls.length,
      0,
    );

    // A page reads at most one source per region — four on the home page — so
    // anything beyond a small multiple of that is a retry loop.
    expect(after - before).toBeLessThanOrEqual(8);
  });

  it("discloses no internal detail in its error state", async () => {
    const { container } = await renderPage(entry, "error");
    const text = container.textContent ?? "";
    // FR-027. The message the mock threw carries a driver name, a host, and a port
    // — the three things a real failure would leak if the cause were passed through.
    expect(text).not.toContain(INTERNAL_DETAIL);
    expect(text).not.toMatch(/psycopg|OperationalError|10\.0\.3\.14|Error:/);
  });

  it("distinguishes its empty state from its error state", async () => {
    // The cheapest way to pass every assertion above is one message shown in both
    // cases, which tells a visitor a company has no services when the database is
    // down. FR-027's whole point is that these are different situations.
    const empty = (await renderPage(entry, "empty")).container.textContent ?? "";
    const failed = (await renderPage(entry, "error")).container.textContent ?? "";
    expect(empty).not.toEqual(failed);
  });
});

describe("a failing region does not take the page with it (FR-030)", () => {
  /**
   * FR-030 requires a failure to stay contained to its own section. The only
   * evidence was `Section.test.tsx`, which exercises the shared component alone —
   * and every page-level sweep in this file fails *all* sources together, which is
   * the one arrangement that cannot demonstrate containment. A page that replaced
   * its entire body with a single error would have passed all of it.
   *
   * `/contact` is the case that matters most: FR-030 is precisely why the form and
   * the office list are separate regions, so a failing office read must leave a
   * visitor able to send a message anyway.
   */
  async function renderWithOneFailure(entry: PageEntry, failing: SourceName) {
    stub("populated");
    (vi.mocked(api)[failing] as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error(INTERNAL_DETAIL),
    );
    const module = await entry.load();
    const Page = module.default as (props: unknown) => ReactNode | Promise<ReactNode>;
    const props = entry.path === "/careers" ? { searchParams: Promise.resolve({}) } : entry.props;
    return render((await resolveServerTree(await Page(props))) as ReactElement);
  }

  const home = REGISTRY.find((entry) => entry.path === "/")!;
  const contact = REGISTRY.find((entry) => entry.path === "/contact")!;

  it("the home page keeps its other regions when news fails", async () => {
    // Four independent regions (FR-005: services, products, news, openings), so this
    // is the sharpest available case. It said "three" until the products summary was
    // added — a count taken from the code rather than from the requirement, which is
    // how a missing region turns into an apparently-cited comment.
    const { container } = await renderWithOneFailure(home, "getNews");
    const text = container.textContent ?? "";

    expect(container.querySelectorAll(ERROR_STATE).length).toBe(1);
    expect(text).toContain("Process Automation"); // services survived
    expect(text).toContain("Horus Ledger"); // products survived
    expect(text).toContain("Platform Engineer"); // vacancies survived
  });

  it("the home page keeps its other regions when services fails", async () => {
    // The same property from the other side: if only the *last* region were
    // resilient, the assertion above would still pass.
    const { container } = await renderWithOneFailure(home, "getServices");
    const text = container.textContent ?? "";

    expect(container.querySelectorAll(ERROR_STATE).length).toBe(1);
    expect(text).toContain("Horus Ledger");
    expect(text).toContain("A release");
    expect(text).toContain("Platform Engineer");
  });

  it("the home page keeps its other regions when products fails", async () => {
    // The region this suite could not have checked before, because the page did not
    // have it.
    const { container } = await renderWithOneFailure(home, "getProducts");
    const text = container.textContent ?? "";

    expect(container.querySelectorAll(ERROR_STATE).length).toBe(1);
    expect(text).toContain("Process Automation");
    expect(text).toContain("A release");
    expect(text).toContain("Platform Engineer");
  });

  it("the contact form stays usable when the office list fails", async () => {
    const { container } = await renderWithOneFailure(contact, "getOffices");

    expect(container.querySelector(ERROR_STATE)).not.toBeNull();
    // The form is the whole point of the page, and it is a separate region.
    expect(container.querySelector("form")).not.toBeNull();
    expect(container.querySelectorAll("input, textarea").length).toBeGreaterThan(2);
  });

  it("one failure is one failure, not a page-wide one", async () => {
    // Guards the count assertions above from passing because the page happens to
    // render no error state at all: with the source failing, exactly one appears.
    const { container } = await renderWithOneFailure(home, "getNews");
    expect(container.querySelectorAll(ERROR_STATE).length).toBe(1);

    const clean = await renderPage(home, "populated");
    expect(clean.container.querySelectorAll(ERROR_STATE).length).toBe(0);
  });
});

describe("which regions actually fetch on the client (FR-025)", () => {
  /**
   * FR-025 names "the careers filter and the contact form" as this feature's only
   * client-fetched regions, and requires those — and only those — to implement a
   * loading state. Half of that sentence is not true of the implementation:
   * `VacancyFilters` is a plain GET form that navigates, so the careers filter is
   * server-rendered and has no loading state to implement.
   *
   * That is the better design — the filter works with JavaScript disabled and the
   * filtered view stays shareable — but it left a requirement whose text pointed at
   * a region that could not satisfy it. These assertions turn the claim into a
   * checked fact, so the classification is verified rather than asserted in prose.
   */
  // Anchored on this file's own directory rather than on `import.meta.url` (not
  // always a `file:` URL under Vitest, and `readdirSync` rejects anything else) or
  // on `process.cwd()` (the runner's, not the package's).
  const root = dirname(fileURLToPath(new URL(import.meta.url)));
  const app = resolve(root, "..");
  const read = (relative: string) => readFileSync(join(app, relative), "utf-8");

  const clientFetchers = () => {
    const found: string[] = [];

    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const child = join(dir, entry.name);
        if (entry.isDirectory()) {
          // `/status` is a non-content route (FR-001a) and predates this feature.
          if (entry.name !== "status") walk(child);
        } else if (entry.name.endsWith(".tsx")) {
          const source = readFileSync(child, "utf-8");
          const isClient = /^\s*["']use client["']/.test(source);
          const fetches = /lib\/api"/.test(source) || /\bfetch\(/.test(source);
          if (isClient && fetches) found.push(entry.name);
        }
      }
    };

    for (const dir of ["components", "app"]) walk(join(app, dir));
    return found.sort();
  };

  /**
   * Every component allowed to fetch from the browser, and why.
   *
   * Kept as an exact set rather than relaxed to "contains", because the value of this
   * assertion is catching the *unexpected* addition — a page that quietly became a
   * client component and started fetching is exactly what FR-025's classification
   * exists to notice.
   *
   * Feature 003 adds two, and both are deliberate. They post to the site's own route
   * handlers rather than to the API, which is the arrangement that keeps the session
   * token in an httpOnly cookie the browser can never read (spec 003 research R3) —
   * so a client component is not an accident here, it is the mechanism.
   */
  const EXPECTED_CLIENT_FETCHERS = [
    // Spec 002 FR-025 — the public site's one write path.
    "ContactForm.tsx",
    // Spec 003 — posts credentials to `/portal/api/login`. Must be a client component:
    // it is a form with per-field errors and a submitting state.
    "SignInForm.tsx",
    // Spec 003 — posts to `/portal/api/logout` with the double-submit CSRF header,
    // which it can only read from `document.cookie`.
    "SignOutButton.tsx",
  ].sort();

  it("only the declared regions fetch from the browser", () => {
    expect(clientFetchers()).toEqual(EXPECTED_CLIENT_FETCHERS);
  });

  it("the public site's only browser fetcher is still the contact form", () => {
    // The half of the original assertion that is about spec 002, stated separately so
    // the portal's arrival cannot quietly weaken it.
    const publicFetchers = clientFetchers().filter(
      (name) => !["SignInForm.tsx", "SignOutButton.tsx"].includes(name),
    );
    expect(publicFetchers).toEqual(["ContactForm.tsx"]);
  });

  it("the careers filter is server-rendered", () => {
    const source = read("components/VacancyFilters.tsx");
    expect(source).not.toMatch(/^\s*["']use client["']/);
    expect(source).toContain('method="get"');
  });

  it("the scan reads real files", () => {
    // Without this, a broken path would make `clientFetchers()` return [] and the
    // first assertion would be comparing nothing to nothing.
    expect(read("components/ContactForm.tsx")).toMatch(/^\s*["']use client["']/);
  });
});

describe("the home page summarizes everything FR-005 names", () => {
  /**
   * The requirement lists four things by name, and the page carried three. Nothing
   * caught it: every check in this file — states, containment, client-fetch
   * classification — asks how the page *behaves*, and none asked what is on it.
   *
   * Driven by the requirement's own list rather than by the page's current
   * contents, so a region removed later fails here instead of quietly shrinking the
   * home page again.
   */
  const REQUIRED_SUMMARIES: { source: SourceName; listing: string }[] = [
    { source: "getServices", listing: "/services" },
    { source: "getProducts", listing: "/products" },
    { source: "getNews", listing: "/news" },
    { source: "getVacancies", listing: "/careers" },
  ];

  const home = REGISTRY.find((entry) => entry.path === "/")!;

  it("reads every source the requirement names", async () => {
    await renderPage(home, "populated");

    for (const { source } of REQUIRED_SUMMARIES) {
      const fn = vi.mocked(api)[source] as unknown as ReturnType<typeof vi.fn>;
      expect(fn.mock.calls.length, `the home page never reads ${source}`).toBeGreaterThan(0);
    }
  });

  it("links each summary to its full page", async () => {
    // FR-005's second clause. The page previously carried zero links to /news,
    // /careers, or /products — the summaries were dead ends.
    const { container } = await renderPage(home, "populated");
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));

    for (const { listing } of REQUIRED_SUMMARIES) {
      expect(hrefs, `the home page does not link to ${listing}`).toContain(listing);
    }
  });

  it("shows content from every summary", async () => {
    const { container } = await renderPage(home, "populated");
    const text = container.textContent ?? "";

    // One distinctive value per required summary, so a region that renders its
    // heading and nothing else does not pass.
    for (const value of ["Process Automation", "Horus Ledger", "A release", "Platform Engineer"]) {
      expect(text, `the home page shows nothing from ${value}`).toContain(value);
    }
  });

  it("the check would notice a missing summary", async () => {
    // Guards the three assertions above. `getProducts` is the one that was absent;
    // confirm the fixture really supplies it, so "reads every source" is testing the
    // page rather than an empty expectation.
    expect(REQUIRED_SUMMARIES).toHaveLength(4);
    expect(SOURCES).toContain("getProducts");
    expect(FIXTURE_VALUES).toContain("Horus Ledger");
  });
});

describe("a field with no value still renders something (FR-008a)", () => {
  /**
   * The fixtures at the top of this file supply a well-formed value for every
   * field, so nothing here has ever rendered a page against empty data. The
   * dataset has no empty fields either, which means this behaviour was reachable
   * from neither direction — the same shape as the closed-vacancy gap T130 closed.
   *
   * FR-008a draws the line: content that is *short but present* is legitimate data
   * and renders as written; content that is empty or whitespace-only renders a
   * defined fallback, never a gap. Both halves are asserted, because an
   * implementation that replaced every short value with a placeholder would satisfy
   * "no blank regions" while destroying real content.
   */
  const BLANK = {
    getCompany: { name: "NileTech Solutions", domain: "niletech.example" },
    getOffices: [{ city: "Cairo", country: "  ", address: "", is_headquarters: true }],
    getServices: [{ name: "Process Automation", summary: "", description: "   ", display_order: 1 }],
    getProducts: [{ name: "Horus Ledger", tagline: "   ", description: "", display_order: 1 }],
    getLeadership: [{ full_name: "Mariam Lotfy", public_title: "", bio: "  ", display_order: 1 }],
    getNews: {
      items: [{ slug: "a-release-abc123", headline: "A release", published_on: "2026-05-01" }],
      total: 1,
    },
    getVacancies: [
      {
        slug: "engineer-abc123",
        title: "Platform Engineer",
        department: "Engineering",
        office_city: "Cairo",
        office_country: "Egypt",
        posted_on: "2026-05-01",
      },
    ],
  } as const;

  /** One word — legitimate content that must survive untouched. */
  const TERSE = {
    ...BLANK,
    getServices: [{ name: "Automation", summary: "Yes.", description: "Ok.", display_order: 1 }],
  } as const;

  async function renderWith(entry: PageEntry, data: Record<string, unknown>) {
    for (const name of SOURCES) {
      const fn = vi.mocked(api)[name] as unknown as ReturnType<typeof vi.fn>;
      fn.mockResolvedValue(structuredClone(data[name]));
    }
    const module = await entry.load();
    const Page = module.default as (props: unknown) => ReactNode | Promise<ReactNode>;
    const props = entry.path === "/careers" ? { searchParams: Promise.resolve({}) } : entry.props;
    return render((await resolveServerTree(await Page(props))) as ReactElement);
  }

  const affected = REGISTRY.filter((entry) =>
    ["/", "/about", "/services", "/products", "/leadership", "/contact"].includes(entry.path),
  );

  it.each(affected)("$path renders no card with a heading above nothing", async (entry) => {
    const { container } = await renderWith(entry, BLANK);

    for (const card of container.querySelectorAll(".eaios-card")) {
      const title = card.querySelector(".eaios-card__title");
      const body = (card.textContent ?? "").replace(title?.textContent ?? "", "").trim();
      expect(body, `a card on ${entry.path} renders only its title`).not.toBe("");
    }
  });

  it.each(affected)("$path marks every absent value for assistive technology", async (entry) => {
    // The visible glyph is an em dash, which means nothing when read aloud, so the
    // fallback carries a real phrase in a screen-reader-only span.
    const { container } = await renderWith(entry, BLANK);
    const absent = container.querySelectorAll(".eaios-text--absent");

    expect(absent.length, `${entry.path} rendered no fallback at all`).toBeGreaterThan(0);
    for (const node of absent) {
      expect(node.querySelector('[aria-hidden="true"]')).not.toBeNull();
      expect(node.querySelector(".sr-only")?.textContent?.trim().length ?? 0).toBeGreaterThan(0);
    }
  });

  it("renders short content as written rather than replacing it", async () => {
    // The other half of FR-008a, and the one an over-eager fallback would break.
    const services = REGISTRY.find((entry) => entry.path === "/services")!;
    const { container } = await renderWith(services, TERSE);
    const text = container.textContent ?? "";

    expect(text).toContain("Yes.");
    expect(text).toContain("Ok.");
    expect(container.querySelectorAll(".eaios-text--absent").length).toBe(0);
  });

  it("the blank fixture really is blank", async () => {
    // Guards both sweeps: if the fixture carried values, "no card renders only its
    // title" would pass for the wrong reason and no fallback would ever appear.
    const values = [
      BLANK.getServices[0].summary,
      BLANK.getProducts[0].tagline,
      BLANK.getLeadership[0].bio,
      BLANK.getOffices[0].address,
    ];
    expect(values.every((value) => value.trim() === "")).toBe(true);
  });
});

describe("detail pages handle an empty field too (FR-008a)", () => {
  /**
   * The registry above is bound to `PUBLIC_PAGES`, which lists the eight content
   * pages a visitor can navigate to directly. Detail routes are reached only through
   * their lists, so they are absent from it — and therefore absent from every sweep
   * in this file, including the empty-field one. That is how an empty news body kept
   * rendering a bare `<p>` under the headline after T133 supposedly closed FR-008a.
   *
   * Declared separately rather than added to `REGISTRY`, because `TestTheListIsBound`
   * asserts that the registry matches the shared page list exactly, and it should:
   * a detail route is not a page in the sense FR-001 means.
   */
  const DETAIL_PAGES = [
    {
      path: "/news/[slug]",
      load: () => import("../app/news/[slug]/page"),
      params: { slug: "a-release-abc123" },
      blank: {
        slug: "a-release-abc123",
        headline: "A release",
        published_on: "2026-05-01",
        body: "   ",
      },
      source: "getNewsItem" as const,
    },
    {
      path: "/careers/[slug]",
      load: () => import("../app/careers/[slug]/page"),
      params: { slug: "engineer-abc123" },
      blank: {
        slug: "engineer-abc123",
        title: "Platform Engineer",
        department: "Engineering",
        office_city: "Cairo",
        office_country: "Egypt",
        posted_on: "2026-05-01",
        description: "",
      },
      source: "getVacancy" as const,
    },
  ];

  it.each(DETAIL_PAGES)("$path renders a fallback rather than an empty block", async (entry) => {
    (vi.mocked(api)[entry.source] as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      structuredClone(entry.blank),
    );

    const module = await entry.load();
    const Page = module.default as (props: unknown) => ReactNode | Promise<ReactNode>;
    const { container } = render(
      (await resolveServerTree(
        await Page({ params: Promise.resolve(entry.params) }),
      )) as ReactElement,
    );

    expect(
      container.querySelectorAll(".eaios-text--absent").length,
      `${entry.path} rendered no fallback for its empty field`,
    ).toBeGreaterThan(0);

    // And no paragraph is left holding nothing, which is the shape the requirement
    // actually forbids.
    for (const paragraph of container.querySelectorAll("p")) {
      expect(paragraph.textContent?.trim(), `${entry.path} has an empty paragraph`).not.toBe("");
    }
  });

  it("the detail pages are genuinely outside the main registry", () => {
    // Guards the reasoning above: if a detail route were ever added to
    // `PUBLIC_PAGES`, this block would be duplicating a sweep rather than filling a
    // hole, and the duplication should be removed rather than left to rot.
    const registered = REGISTRY.map((entry) => entry.path);
    for (const entry of DETAIL_PAGES) {
      expect(registered).not.toContain(entry.path);
    }
  });
});
