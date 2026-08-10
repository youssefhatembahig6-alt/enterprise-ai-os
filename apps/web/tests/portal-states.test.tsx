/**
 * Every portal surface renders every state it can reach (spec 003 FR-027, FR-029,
 * SC-009; contracts/portal-routes.md §3; tasks T079, T092).
 *
 * `state-coverage.test.tsx` does this for the eight *public* pages and is bound to
 * `PUBLIC_PAGES`, so it never reached the portal.
 *
 * **The matrix is declared, not implied.** §3 says "every portal surface implements
 * all of these", and a literal reading is a 5 × 7 rectangle in which nine cells are
 * nonsense: `/portal/denied` fetches nothing, so it has no populated or empty state to
 * render; `/portal/home` reads `/me`, which no authenticated caller can be forbidden
 * from; a profile resolves or it does not, so there is no empty profile. Writing tests
 * for those would mean adding fetches to pages that need none.
 *
 * So every cell is classified below as one of three things — route-specific, proven at
 * a shared boundary, or unreachable with a stated reason — and `TestTheMatrixIsTotal`
 * fails if any route or state is missing a classification. An unreachable cell has to
 * say *why*, in the file, where the next person reading it can disagree.
 *
 * Shared boundaries are tested once and their reach is proven separately: a redirect
 * asserted four times over is one fact tested once and counted four times. What makes
 * the sharing sound is that every portal route is nested beneath the boundary, and
 * that is asserted directly against the route tree.
 */

import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTAL_DYNAMIC_ROUTES, PORTAL_PAGES } from "../lib/pages";
import * as portalApi from "../lib/portal-api";
import type { CurrentUser, DirectReport, HrProfile } from "../lib/portal-api";
import * as session from "../lib/session";
import { notFound, redirect } from "next/navigation";

/**
 * The real module, with only the fetchers replaced. The error classes must stay real:
 * every page and the shell branch with `instanceof`, so mocked classes would send all
 * four outcomes down one path and the distinctions this file exists to check would
 * evaporate while every test still passed.
 */
vi.mock("../lib/portal-api", async (importOriginal) => {
  const actual = await importOriginal<typeof portalApi>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    getOwnProfile: vi.fn(),
    getDirectReports: vi.fn(),
    getProfile: vi.fn(),
  };
});

vi.mock("../lib/session", () => ({
  sessionToken: vi.fn(),
  authHeaders: vi.fn(),
}));

/** Next signals both by throwing; the tag lets a test assert which one was reached.
 *  `useRouter` is stubbed as `SignInForm.test.tsx` does — the form navigates on
 *  success and would throw outside a router. */
vi.mock("next/navigation", () => ({
  redirect: vi.fn((path: string) => {
    throw new Error(`NEXT_REDIRECT:${path}`);
  }),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

/** The rejection every failing source throws — distinctive, so FR-022's prohibition on
 *  leaking internal detail is checked by searching the rendered markup for it. */
const INTERNAL_DETAIL = "psycopg.OperationalError at 10.0.3.14:5432";

/** Strings that must never reach a portal surface in any state. */
const MUST_NEVER_APPEAR = [
  INTERNAL_DETAIL,
  "psycopg",
  "10.0.3.14",
  "Traceback",
  "eyJhbGciOi", // a JWT's opening bytes
  "salary",
  "salary_amount",
];

const EMPTY_STATE = '.eaios-state[role="status"]:not(.eaios-state--expired)';
const ERROR_STATE = ".eaios-state--error[role='alert']";
const DENIED_STATE = ".eaios-state--denied[role='alert']";
const EXPIRED_STATE = ".eaios-state--expired[role='status']";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "../app");
const AUTHED_GROUP = "app/portal/(authed)";

// ---------------------------------------------------------------------------
// The matrix
// ---------------------------------------------------------------------------

const STATES = [
  "loading",
  "populated",
  "empty",
  "error",
  "unauthenticated",
  "expired",
  "denied",
] as const;
type State = (typeof STATES)[number];

type Cell =
  /** Rendered by this route's own code, and driven into that state below. */
  | { kind: "route" }
  /** Proven once against the named boundary; this route's nesting is proven too. */
  | { kind: "shared"; boundary: string }
  /** Cannot occur. The reason is the assertion — it is what a reviewer argues with. */
  | { kind: "unreachable"; reason: string };

const LOADING_BOUNDARY = `${AUTHED_GROUP}/loading.tsx`;
const ERROR_BOUNDARY = "app/portal/error.tsx";
const SHELL = `${AUTHED_GROUP}/layout.tsx`;

const shared = (boundary: string): Cell => ({ kind: "shared", boundary });
const unreachable = (reason: string): Cell => ({ kind: "unreachable", reason });
const route: Cell = { kind: "route" };

/** Every portal route, static and dynamic, against every state §3 names. */
const MATRIX: Record<string, Record<State, Cell>> = {
  "/portal/home": {
    loading: shared(LOADING_BOUNDARY),
    populated: route,
    empty: route,
    error: shared(ERROR_BOUNDARY),
    unauthenticated: shared(SHELL),
    expired: shared(SHELL),
    denied: unreachable(
      "its only read is /me, which every authenticated caller may make; there is no 403 to render",
    ),
  },
  "/portal/profile": {
    loading: shared(LOADING_BOUNDARY),
    populated: route,
    empty: route,
    error: route,
    unauthenticated: shared(SHELL),
    expired: shared(SHELL),
    denied: route,
  },
  "/portal/team": {
    loading: shared(LOADING_BOUNDARY),
    populated: route,
    empty: route,
    error: route,
    unauthenticated: shared(SHELL),
    expired: shared(SHELL),
    denied: route,
  },
  "/portal/denied": {
    loading: shared(LOADING_BOUNDARY),
    populated: unreachable("the page reads nothing; the denial is the whole surface"),
    empty: unreachable("the page reads nothing, so it has no result that could be empty"),
    error: shared(ERROR_BOUNDARY),
    unauthenticated: shared(SHELL),
    expired: shared(SHELL),
    denied: route,
  },
  "/portal/team/[userId]": {
    loading: shared(LOADING_BOUNDARY),
    populated: route,
    empty: unreachable("a profile resolves, is refused, or is absent; there is no empty profile"),
    error: route,
    unauthenticated: shared(SHELL),
    expired: shared(SHELL),
    denied: route,
  },
};

/** Route → the module that serves it. Used to prove nesting beneath the boundaries. */
const ROUTE_FILES: Record<string, string> = {
  "/portal/home": `${AUTHED_GROUP}/home/page.tsx`,
  "/portal/profile": `${AUTHED_GROUP}/profile/page.tsx`,
  "/portal/team": `${AUTHED_GROUP}/team/page.tsx`,
  "/portal/denied": `${AUTHED_GROUP}/denied/page.tsx`,
  "/portal/team/[userId]": `${AUTHED_GROUP}/team/[userId]/page.tsx`,
};

const ALL_ROUTES = [...PORTAL_PAGES, ...PORTAL_DYNAMIC_ROUTES.map((r) => r.pattern)];

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMPLOYEE_PERMISSIONS = ["documents:read", "hr:read_self"];
const MANAGER_PERMISSIONS = [...EMPLOYEE_PERMISSIONS, "hr:read_team"];

function user(permissions: string[] = MANAGER_PERMISSIONS): CurrentUser {
  return {
    user_id: "00000000-0000-0000-0000-000000000001",
    full_name: "Latifa AlNuaimi",
    email: "latifa.alnuaimi@niletech.example",
    company_name: "NileTech Solutions",
    department: "Engineering",
    office: "Dubai",
    roles: ["Employee"],
    permissions,
  } as CurrentUser;
}

const PROFILE: HrProfile = {
  full_name: "Latifa AlNuaimi",
  job_title: "Senior Engineer",
  department: "Engineering",
  office: "Dubai",
  manager_name: "Farida Mansour",
  employment_type: "FULL_TIME",
  hire_date: "2021-03-01",
  leave_balance: { entitlement_days: 22, used_days: 2, remaining_days: 20 },
} as HrProfile;

const REPORT_USER_ID = "00000000-0000-0000-0000-000000000002";

const REPORTS: DirectReport[] = [
  {
    user_id: REPORT_USER_ID,
    full_name: "Omar Adel",
    job_title: "Engineer",
    department: "Engineering",
  } as DirectReport,
];

/**
 * Resolves async server components so their rendered output can be asserted.
 *
 * Async components are identified by their constructor rather than by calling them to
 * see what comes back: calling a *client* component directly would run its hooks
 * outside a render and throw. `state-coverage.test.tsx` carries the same walk for the
 * public pages; it lives beside its only caller in both files rather than pulling a
 * shared test-infrastructure module into existence for a dozen lines.
 */
const isAsyncComponent = (type: unknown): type is (props: unknown) => Promise<ReactNode> =>
  typeof type === "function" && type.constructor?.name === "AsyncFunction";

async function resolveServerTree(node: ReactNode): Promise<ReactNode> {
  if (Array.isArray(node)) {
    const resolved = await Promise.all(node.map(resolveServerTree));
    // A resolved async component is a fresh element with no key, so the list it came
    // from would warn. A positional key keeps the output identical and the run free of
    // noise that would mask a real warning.
    return resolved.map((child, index) =>
      isValidElement(child) && child.key === null ? cloneElement(child, { key: index }) : child,
    ) as ReactNode;
  }
  if (!isValidElement(node)) return node;

  const element = node as ReactElement<{ children?: ReactNode }>;
  if (isAsyncComponent(element.type)) {
    return resolveServerTree(await element.type(element.props));
  }
  if (typeof element.type !== "function" && element.props?.children !== undefined) {
    return cloneElement(element, {}, await resolveServerTree(element.props.children));
  }
  return element;
}

const mocked = vi.mocked(portalApi);

type Arranger = () => void;

/** How each route-specific cell is driven. Bound to the matrix by `TestTheMatrixIsTotal`. */
const ARRANGE: Record<string, Partial<Record<State, Arranger>>> = {
  "/portal/home": {
    populated: () => mocked.getCurrentUser.mockResolvedValue(user()),
    // The specification's "a user with no roles at all": signed in, nowhere to go.
    empty: () => mocked.getCurrentUser.mockResolvedValue(user([])),
  },
  "/portal/profile": {
    populated: () => mocked.getOwnProfile.mockResolvedValue(structuredClone(PROFILE)),
    // "No balance recorded" and "zero days remaining" are different facts.
    empty: () =>
      mocked.getOwnProfile.mockResolvedValue({ ...structuredClone(PROFILE), leave_balance: null }),
    error: () => mocked.getOwnProfile.mockRejectedValue(new Error(INTERNAL_DETAIL)),
    denied: () => mocked.getOwnProfile.mockRejectedValue(new portalApi.ForbiddenError()),
  },
  "/portal/team": {
    populated: () => mocked.getDirectReports.mockResolvedValue(structuredClone(REPORTS)),
    empty: () => mocked.getDirectReports.mockResolvedValue([]),
    error: () => mocked.getDirectReports.mockRejectedValue(new Error(INTERNAL_DETAIL)),
    denied: () => mocked.getDirectReports.mockRejectedValue(new portalApi.ForbiddenError()),
  },
  "/portal/denied": {
    denied: () => undefined,
  },
  "/portal/team/[userId]": {
    populated: () => mocked.getProfile.mockResolvedValue(structuredClone(PROFILE)),
    error: () => mocked.getProfile.mockRejectedValue(new Error(INTERNAL_DETAIL)),
    denied: () => mocked.getProfile.mockRejectedValue(new portalApi.ForbiddenError()),
  },
};

const LOAD: Record<string, () => Promise<{ default: unknown }>> = {
  "/portal/home": () => import("../app/portal/(authed)/home/page"),
  "/portal/profile": () => import("../app/portal/(authed)/profile/page"),
  "/portal/team": () => import("../app/portal/(authed)/team/page"),
  "/portal/denied": () => import("../app/portal/(authed)/denied/page"),
  "/portal/team/[userId]": () => import("../app/portal/(authed)/team/[userId]/page"),
};

async function renderRoute(routePath: string, state: State) {
  ARRANGE[routePath]?.[state]?.();
  const module = await LOAD[routePath]!();
  const Page = module.default as (props: unknown) => ReactNode | Promise<ReactNode>;
  const props =
    routePath === "/portal/team/[userId]"
      ? { params: Promise.resolve({ userId: REPORT_USER_ID }) }
      : undefined;
  return render((await resolveServerTree(await Page(props))) as ReactElement);
}

function assertNothingSensitive(container: HTMLElement): void {
  const markup = container.innerHTML;
  for (const secret of MUST_NEVER_APPEAR) {
    expect(markup.toLowerCase()).not.toContain(secret.toLowerCase());
  }
}

/**
 * Matrix lookups that refuse to be absent.
 *
 * `noUncheckedIndexedAccess` would otherwise let an unclassified route read as
 * `undefined` and quietly satisfy a `!== "unreachable"` comparison — the classification
 * gap the matrix exists to catch, hidden by the type system's own escape hatch.
 */
function cellFor(path: string, state: State): Cell {
  const row = MATRIX[path];
  if (!row) throw new Error(`route ${path} has no classification row`);
  return row[state];
}

function fileFor(path: string): string {
  const file = ROUTE_FILES[path];
  if (!file) throw new Error(`route ${path} has no module mapped`);
  return file;
}

/** Routes whose matrix marks a state as route-specific. */
const routesWith = (state: State) =>
  ALL_ROUTES.filter((path) => cellFor(path, state).kind === "route");

beforeEach(() => {
  vi.mocked(session.sessionToken).mockResolvedValue(null);
  vi.mocked(session.authHeaders).mockResolvedValue({ Authorization: "Bearer test" });
});

afterEach(() => {
  vi.resetAllMocks();
});

// ---------------------------------------------------------------------------

describe("TestTheMatrixIsTotal", () => {
  it("classifies every route in the shared inventory, and no others", () => {
    // Both directions, and both inventories. A portal page added to `PORTAL_PAGES` or a
    // dynamic route added to `PORTAL_DYNAMIC_ROUTES` without a row fails here.
    expect(Object.keys(MATRIX).sort()).toEqual([...ALL_ROUTES].sort());
  });

  it("classifies every state on every route", () => {
    const unclassified: string[] = [];
    for (const [path, row] of Object.entries(MATRIX)) {
      for (const state of STATES) {
        if (!row[state]) unclassified.push(`${path} × ${state}`);
      }
    }
    expect(unclassified).toEqual([]);
  });

  it("every unreachable cell states a reason", () => {
    for (const [path, row] of Object.entries(MATRIX)) {
      for (const state of STATES) {
        const cell = row[state];
        if (cell.kind === "unreachable") {
          expect(cell.reason.length, `${path} × ${state}`).toBeGreaterThan(20);
        }
      }
    }
  });

  it("every route-specific cell has a way to be driven into that state", () => {
    // Keeps the matrix and the tests honest about each other: a cell claiming to be
    // route-specific with no arranger would be a classification nobody exercises.
    const missing: string[] = [];
    for (const [path, row] of Object.entries(MATRIX)) {
      for (const state of STATES) {
        if (row[state].kind === "route" && !ARRANGE[path]?.[state]) missing.push(`${path} × ${state}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("no arranger exists for a cell the matrix does not call route-specific", () => {
    const stray: string[] = [];
    for (const [path, states] of Object.entries(ARRANGE)) {
      for (const state of Object.keys(states) as State[]) {
        if (MATRIX[path]?.[state]?.kind !== "route") stray.push(`${path} × ${state}`);
      }
    }
    expect(stray).toEqual([]);
  });

  it("every state §3 names is reachable somewhere in the portal", () => {
    for (const state of STATES) {
      const reachable = ALL_ROUTES.some((p) => cellFor(p, state).kind !== "unreachable");
      expect(reachable, `${state} is unreachable on every route`).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Route-specific states
// ---------------------------------------------------------------------------

describe.each(routesWith("populated"))("%s — populated", (routePath) => {
  it("renders its content when the request succeeds", async () => {
    const { container } = await renderRoute(routePath, "populated");
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(container.querySelector(EMPTY_STATE)).toBeNull();
    expect(container.querySelector(ERROR_STATE)).toBeNull();
    expect(container.querySelector(DENIED_STATE)).toBeNull();
    assertNothingSensitive(container);
  });
});

describe.each(routesWith("empty"))("%s — empty", (routePath) => {
  it("announces an empty result and offers a way onward", async () => {
    const { container } = await renderRoute(routePath, "empty");
    const empty = container.querySelector(EMPTY_STATE);
    expect(empty).not.toBeNull();
    // `role="status"`, not `alert`: nothing is wrong, so it must not interrupt.
    expect(empty).toHaveAttribute("role", "status");
    expect(empty?.textContent?.trim().length ?? 0).toBeGreaterThan(20);
    // A dead end is the defect; every empty state carries an action.
    expect(container.querySelector(".eaios-actions a, .eaios-state a")).not.toBeNull();
    expect(container.querySelector(ERROR_STATE)).toBeNull();
    expect(container.querySelector(DENIED_STATE)).toBeNull();
    assertNothingSensitive(container);
  });
});

describe.each(routesWith("error"))("%s — error", (routePath) => {
  it("reports a failure without disclosing any of it, and wires a retry", async () => {
    const { container } = await renderRoute(routePath, "error");
    const error = container.querySelector(ERROR_STATE);
    expect(error).not.toBeNull();
    // `role="alert"`: the page the person asked for is absent, so it interrupts.
    expect(error).toHaveAttribute("role", "alert");
    // FR-022 — the rejection carried a driver name, a host, and a port.
    assertNothingSensitive(container);
    const retry = screen.getByRole("link", { name: /try again/i });
    // Wired: it returns to the surface that failed, not to a generic page.
    expect(retry.getAttribute("href")).toContain("/portal/");
    // A failure must not be mistaken for "there is nothing here".
    expect(container.querySelector(EMPTY_STATE)).toBeNull();
  });
});

describe.each(routesWith("denied"))("%s — access denied", (routePath) => {
  it("shows a designed refusal, not a blank screen", async () => {
    const { container } = await renderRoute(routePath, "denied");
    const denied = container.querySelector(DENIED_STATE);
    expect(denied).not.toBeNull();
    expect(denied).toHaveAttribute("role", "alert");
    // Informative: what happened, and who can change it (FR-029).
    expect(denied?.textContent ?? "").toMatch(/permission|access|report/i);
    // FR-022 — never which permission is missing, which is a map for someone probing.
    expect(container.innerHTML).not.toMatch(/hr:read_|documents:read|actions:approve/);
    assertNothingSensitive(container);
    // Denied is not empty: collapsing them sends the person to the wrong help.
    expect(container.querySelector(EMPTY_STATE)).toBeNull();
  });
});

describe("empty and access-denied stay distinct on the same surface", () => {
  it("a permitted manager with no reports is told the team is empty, not that they lack access", async () => {
    const { container } = await renderRoute("/portal/team", "empty");
    expect(container.querySelector(EMPTY_STATE)?.textContent).toMatch(/nobody reports to you/i);
    expect(container.querySelector(DENIED_STATE)).toBeNull();
  });

  it("a caller without the permission is refused, not told the team is empty", async () => {
    const { container } = await renderRoute("/portal/team", "denied");
    expect(container.querySelector(DENIED_STATE)?.textContent).toMatch(/do not manage a team/i);
    expect(container.querySelector(EMPTY_STATE)).toBeNull();
    expect(container.textContent).not.toMatch(/nobody reports to you/i);
  });
});

// ---------------------------------------------------------------------------
// Shared boundaries — tested once, reach proven separately
// ---------------------------------------------------------------------------

describe(`shared boundary: ${SHELL} (unauthenticated, expired)`, () => {
  async function renderShell() {
    const module = await import("../app/portal/(authed)/layout");
    const Layout = module.default as (props: unknown) => Promise<ReactNode>;
    return Layout({ children: null });
  }

  it("an authenticated caller is not redirected anywhere", async () => {
    mocked.getCurrentUser.mockResolvedValue(user());
    await expect(renderShell()).resolves.toBeTruthy();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("a caller with no session is sent to the portal address", async () => {
    mocked.getCurrentUser.mockRejectedValue(new portalApi.UnauthenticatedError());
    await expect(renderShell()).rejects.toThrow("NEXT_REDIRECT:/portal");
    expect(redirect).toHaveBeenCalledWith("/portal");
  });

  it("a caller whose session ended is sent to the same place, which decides the wording", async () => {
    mocked.getCurrentUser.mockRejectedValue(new portalApi.SessionExpiredError());
    await expect(renderShell()).rejects.toThrow("NEXT_REDIRECT:/portal");
    expect(redirect).toHaveBeenCalledWith("/portal");
  });

  it("a dependency failure is NOT sent to the sign-in form", async () => {
    // The defect this shell used to have: a bare `catch` told a signed-in person during
    // an outage that they were signed out, collapsing *error* into *unauthenticated* —
    // the pair §3 says must stay distinct. It rethrows now, for the boundary to catch.
    mocked.getCurrentUser.mockRejectedValue(new Error(INTERNAL_DETAIL));
    await expect(renderShell()).rejects.toThrow(INTERNAL_DETAIL);
    expect(redirect).not.toHaveBeenCalled();
  });

  it("every route classified as sharing it is nested beneath it", () => {
    const sharing = ALL_ROUTES.filter((p) =>
      (["unauthenticated", "expired"] as State[]).some((s) => {
        const cell = cellFor(p, s);
        return cell.kind === "shared" && cell.boundary === SHELL;
      }),
    );
    expect(sharing.sort()).toEqual([...ALL_ROUTES].sort());
    // Nesting is a filesystem fact in Next, so it is asserted against the tree.
    expect(existsSync(resolve(APP, "portal/(authed)/layout.tsx"))).toBe(true);
    for (const path of sharing) {
      expect(fileFor(path), path).toContain(`${AUTHED_GROUP}/`);
      expect(existsSync(resolve(APP, "..", fileFor(path))), fileFor(path)).toBe(true);
    }
  });
});

describe(`shared boundary: ${LOADING_BOUNDARY} (loading)`, () => {
  it("shows a skeleton shaped like the page, not a blank pane", async () => {
    const module = await import("../app/portal/(authed)/loading");
    const Loading = module.default as () => ReactNode;
    const { container } = render(<>{Loading()}</>);

    // §3: "a skeleton matching the final layout, never a spinner over a blank page".
    const bars = container.querySelectorAll(".eaios-skeleton");
    expect(bars.length).toBeGreaterThan(1);
    expect(container.textContent?.trim()).not.toBe("");
  });

  it("announces the wait without reading the skeleton aloud", async () => {
    const module = await import("../app/portal/(authed)/loading");
    const Loading = module.default as () => ReactNode;
    const { container } = render(<>{Loading()}</>);

    const status = container.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status?.textContent ?? "").toMatch(/loading/i);
    // `role="status"`, not `alert`: waiting is not an error.
    expect(container.querySelector('[role="alert"]')).toBeNull();
    // The bars themselves are hidden — announcing a shimmering box says nothing.
    expect(container.querySelector('[aria-hidden="true"] .eaios-skeleton')).not.toBeNull();
  });

  it("covers every route classified as sharing it", () => {
    const sharing = ALL_ROUTES.filter((p) => {
      const cell = cellFor(p, "loading");
      return cell.kind === "shared" && cell.boundary === LOADING_BOUNDARY;
    });
    expect(sharing.sort()).toEqual([...ALL_ROUTES].sort());
    // One file in the route group serves all of them; Next wraps a segment's children
    // in the Suspense boundary it declares.
    expect(existsSync(resolve(APP, "portal/(authed)/loading.tsx"))).toBe(true);
    for (const path of sharing) {
      expect(fileFor(path), path).toContain(`${AUTHED_GROUP}/`);
    }
  });
});

describe(`shared boundary: ${ERROR_BOUNDARY} (error)`, () => {
  it("is at the parent segment, because a boundary cannot catch its own layout", () => {
    // Next renders `error.tsx` *inside* the layout of its segment, so a boundary beside
    // `(authed)/layout.tsx` could never catch that layout's throw — which is the one
    // failure most worth catching, since the shell is where identity is fetched.
    expect(existsSync(resolve(APP, "portal/error.tsx"))).toBe(true);
    expect(existsSync(resolve(APP, "portal/(authed)/error.tsx"))).toBe(false);
  });

  it("renders a designed failure that discloses nothing", async () => {
    const module = await import("../app/portal/error");
    const PortalError = module.default as (props: {
      error: Error;
      reset: () => void;
    }) => ReactNode;
    const { container } = render(
      <>{PortalError({ error: new Error(INTERNAL_DETAIL), reset: vi.fn() })}</>,
    );

    const error = container.querySelector(ERROR_STATE);
    expect(error).not.toBeNull();
    expect(error).toHaveAttribute("role", "alert");
    // The error object carried a driver name, host, and port; none of it is rendered.
    assertNothingSensitive(container);
    // Silent about authentication in *both* directions. This boundary also catches
    // shell failures, which happen before identity is known — so "you were signed out"
    // would be the collapse §3 forbids, and "you are still signed in" would be a guess
    // that is wrong precisely when the session had ended.
    expect(container.textContent ?? "").not.toMatch(
      /signed out|session has ended|sign in again|still signed in|signed in/i,
    );
    // What it does say: what failed, and what to do about it.
    expect(container.textContent ?? "").toMatch(/could not be loaded/i);
    expect(container.textContent ?? "").toMatch(/IT team/i);
  });

  it("its retry is genuinely wired to the boundary's reset", async () => {
    const reset = vi.fn();
    const module = await import("../app/portal/error");
    const PortalError = module.default as (props: {
      error: Error;
      reset: () => void;
    }) => ReactNode;
    render(<>{PortalError({ error: new Error("x"), reset })}</>);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("covers every route classified as sharing it", () => {
    const sharing = ALL_ROUTES.filter((p) => {
      const cell = cellFor(p, "error");
      return cell.kind === "shared" && cell.boundary === ERROR_BOUNDARY;
    });
    // Only the routes with no error state of their own — the rest handle it inline.
    expect(sharing.sort()).toEqual(["/portal/denied", "/portal/home"]);
    for (const path of sharing) {
      expect(fileFor(path), path).toContain(`${AUTHED_GROUP}/`);
    }
  });
});

describe("/portal tells an ended session apart from never having signed in", () => {
  async function renderSignInPage() {
    const module = await import("../app/portal/page");
    const Page = module.default as () => Promise<ReactNode>;
    return render((await resolveServerTree(await Page())) as ReactElement);
  }

  it("no cookie: the form, and no claim that anything expired", async () => {
    vi.mocked(session.sessionToken).mockResolvedValue(null);
    const { container } = await renderSignInPage();
    expect(screen.getByLabelText(/work email address/i)).toBeInTheDocument();
    expect(container.querySelector(EXPIRED_STATE)).toBeNull();
    expect(container.textContent).not.toMatch(/signed out|session has ended/i);
  });

  it("a cookie the server no longer accepts: the expired state, above the form", async () => {
    vi.mocked(session.sessionToken).mockResolvedValue("stale-token");
    mocked.getCurrentUser.mockRejectedValue(new portalApi.SessionExpiredError());
    const { container } = await renderSignInPage();

    const expired = container.querySelector(EXPIRED_STATE);
    expect(expired).not.toBeNull();
    // `role="status"`, not `alert`: being signed out is expected, not an error.
    expect(expired).toHaveAttribute("role", "status");
    expect(expired?.textContent ?? "").toMatch(/signed out|session has ended/i);
    // The way back in is still on the page — an expired state with no form is a trap.
    expect(screen.getByLabelText(/work email address/i)).toBeInTheDocument();
    assertNothingSensitive(container);
  });

  it("a dependency failure is rethrown to the portal error boundary, not dressed as a sign-out", async () => {
    // It used to fall through to the form, so an outage was indistinguishable from a
    // signed-out visitor: sign in, fail again, no explanation. The failure now leaves
    // this page for `app/portal/error.tsx` to render.
    vi.mocked(session.sessionToken).mockResolvedValue("stale-token");
    mocked.getCurrentUser.mockRejectedValue(new Error(INTERNAL_DETAIL));

    const module = await import("../app/portal/page");
    const Page = module.default as () => Promise<ReactNode>;
    await expect(Page()).rejects.toThrow(INTERNAL_DETAIL);
    expect(redirect).not.toHaveBeenCalled();
  });

  it("no usable credential is still the form, not an error", async () => {
    // `UnauthenticatedError` is not a dependency failure — it means there is nothing to
    // sign in with, and the form is the right answer. Rethrowing it would put an error
    // page in front of every first-time visitor.
    vi.mocked(session.sessionToken).mockResolvedValue("stale-token");
    mocked.getCurrentUser.mockRejectedValue(new portalApi.UnauthenticatedError());
    const { container } = await renderSignInPage();
    expect(screen.getByLabelText(/work email address/i)).toBeInTheDocument();
    expect(container.querySelector(EXPIRED_STATE)).toBeNull();
  });
});

describe("the sign-in form's own loading state", () => {
  it("says it is working, and stops accepting a second submission", async () => {
    // `/portal` sits outside the `(authed)` group and has no Suspense boundary: it
    // renders a form, and the wait that matters is the submission. Held open by a
    // promise that never settles.
    const pending = new Promise<Response>(() => {});
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));

    const { SignInForm } = await import("../components/portal/SignInForm");
    render(<SignInForm />);

    await userEvent.type(screen.getByLabelText(/work email address/i), "a@niletech.example");
    await userEvent.type(screen.getByLabelText(/password/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    const button = screen.getByRole("button", { name: /signing in|sign in/i });
    await waitFor(() => expect(button).toBeDisabled());
    await waitFor(() => expect(button).toHaveTextContent(/signing in/i));

    vi.unstubAllGlobals();
  });
});

// ---------------------------------------------------------------------------

describe("the dynamic team-member route", () => {
  const dynamic = PORTAL_DYNAMIC_ROUTES.find((r) => r.id === "team-member")!;

  it("is declared in the inventory without a template a browser sweep could visit", () => {
    expect(dynamic.pattern).toBe("/portal/team/[userId]");
    // The built address is concrete, and no `PORTAL_PAGES` consumer ever sees the
    // pattern — a sweep sent to the literal `[userId]` would 404 and report the portal
    // as broken.
    expect(dynamic.href(REPORT_USER_ID)).toBe(`/portal/team/${REPORT_USER_ID}`);
    expect([...PORTAL_PAGES]).not.toContain(dynamic.pattern);
  });

  it("another tenant's identifier is not found, never refused", async () => {
    // Rendering the refusal here would confirm the record exists, which is the
    // enumeration the tenant boundary's placement at layer 1 exists to prevent.
    //
    // Driven directly rather than through `renderRoute`: not-found is not a matrix
    // state, and going through the arrangers would overwrite this rejection with one
    // of them.
    mocked.getProfile.mockRejectedValue(new portalApi.PortalNotFoundError());
    const module = await import("../app/portal/(authed)/team/[userId]/page");
    const Page = module.default as (props: unknown) => Promise<ReactNode>;
    await expect(Page({ params: Promise.resolve({ userId: REPORT_USER_ID }) })).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(notFound).toHaveBeenCalled();
  });

  it("a refusal keeps a way back to the team it came from", async () => {
    const { container } = await renderRoute("/portal/team/[userId]", "denied");
    expect(container.querySelector(DENIED_STATE)).not.toBeNull();
    expect(screen.getByRole("link", { name: /my team/i })).toHaveAttribute("href", "/portal/team");
    expect(notFound).not.toHaveBeenCalled();
  });
});
