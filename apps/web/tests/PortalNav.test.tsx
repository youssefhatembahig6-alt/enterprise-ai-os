/**
 * Role-aware navigation (spec 003 FR-014, FR-028, SC-008).
 *
 * The constitution: "a user never sees an entry point to something they cannot use."
 *
 * Two things make this file worth more than a rendering check.
 *
 * **Every hiding assertion is paired with a showing one, in the same test.** A
 * component that rendered *no* navigation at all would satisfy every "the entry is
 * absent" assertion in isolation, and pass a whole suite while being completely
 * broken.
 *
 * **Absent, not hidden.** `display: none` is still in the DOM, still in the page
 * source, and still — depending on how it was hidden — in the accessibility tree.
 * These tests assert the string does not appear in the markup at all.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PORTAL_ENTRIES, PortalNav, visibleEntries } from "../components/portal/PortalNav";
import type { CurrentUser } from "../lib/portal-api";

function user(permissions: string[]): CurrentUser {
  return {
    user_id: "00000000-0000-0000-0000-000000000001",
    full_name: "Test Person",
    email: "test@niletech.example",
    company_name: "NileTech Solutions",
    department: "Engineering",
    office: "Cairo",
    roles: ["Employee"],
    permissions,
  } as CurrentUser;
}

const EMPLOYEE = ["documents:read", "hr:read_self"];
const MANAGER = [...EMPLOYEE, "hr:read_team", "actions:approve"];

describe("the fixture is meaningful", () => {
  it("the entry list is not empty", () => {
    expect(PORTAL_ENTRIES.length).toBeGreaterThan(0);
  });

  it("at least one entry is permission-gated and one is not", () => {
    // Without both, every test below is checking one uniform behaviour and calling it
    // two different things.
    expect(PORTAL_ENTRIES.some((e) => e.permission !== null)).toBe(true);
    expect(PORTAL_ENTRIES.some((e) => e.permission === null)).toBe(true);
  });

  it("the manager fixture is a superset of the employee one", () => {
    expect(MANAGER).toEqual(expect.arrayContaining(EMPLOYEE));
    expect(MANAGER.length).toBeGreaterThan(EMPLOYEE.length);
  });
});

describe("entries appear only for the permission that grants them", () => {
  it("a manager sees My team and an employee does not", () => {
    // The pair, in one test, on purpose. Either assertion alone is satisfiable by a
    // broken component.
    const { unmount } = render(<PortalNav user={user(MANAGER)} />);
    expect(screen.getByRole("link", { name: /my team/i })).toBeInTheDocument();
    unmount();

    const { container } = render(<PortalNav user={user(EMPLOYEE)} />);
    expect(screen.queryByRole("link", { name: /my team/i })).toBeNull();
    expect(container.innerHTML).not.toContain("/portal/team");
  });

  it("both see the entries they do hold", () => {
    for (const permissions of [EMPLOYEE, MANAGER]) {
      const { unmount } = render(<PortalNav user={user(permissions)} />);
      expect(screen.getByRole("link", { name: /^home$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /my hr profile/i })).toBeInTheDocument();
      unmount();
    }
  });

  it("a user with no permissions still sees the ungated entries", () => {
    // The spec's edge case: a user with no roles at all must still sign in and see a
    // portal, not an empty frame.
    render(<PortalNav user={user([])} />);
    expect(screen.getByRole("link", { name: /^home$/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /my hr profile/i })).toBeNull();
  });
});

describe("hidden means absent from the markup", () => {
  it("no href for a withheld area appears anywhere in the HTML", () => {
    const { container } = render(<PortalNav user={user([])} />);
    for (const entry of PORTAL_ENTRIES.filter((e) => e.permission !== null)) {
      expect(container.innerHTML).not.toContain(entry.href);
    }
  });

  it("nothing is merely visually hidden", () => {
    const { container } = render(<PortalNav user={user([])} />);
    expect(container.querySelectorAll("[hidden]")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("display: none");
    expect(container.innerHTML).not.toContain("display:none");
  });
});

describe("decisions are made from permission codes, never role names", () => {
  it("a role name alone grants nothing", () => {
    // FR-014. Someone labelled Manager without `hr:read_team` must not see the team
    // area — the label is data an administrator edits, the code is the grant.
    const impostor = { ...user([]), roles: ["Manager", "Company Admin", "HR"] };
    const { container } = render(<PortalNav user={impostor} />);
    expect(container.innerHTML).not.toContain("/portal/team");
  });

  it("the code alone grants it, whatever the role says", () => {
    const unlabelled = { ...user(["hr:read_team"]), roles: [] };
    render(<PortalNav user={unlabelled} />);
    expect(screen.getByRole("link", { name: /my team/i })).toBeInTheDocument();
  });
});

describe("the navigation is a landmark", () => {
  it("is labelled so a screen-reader user can skip to or past it", () => {
    render(<PortalNav user={user(MANAGER)} />);
    expect(screen.getByRole("navigation", { name: /portal/i })).toBeInTheDocument();
  });
});

describe("visibleEntries is the single source the pages share", () => {
  it("returns exactly what the component renders", () => {
    // The home page lists reachable areas from this same function. If they diverged,
    // the navigation and the page body would disagree about where you can go.
    const permissions = MANAGER;
    const { container } = render(<PortalNav user={user(permissions)} />);
    for (const entry of visibleEntries(user(permissions))) {
      expect(container.innerHTML).toContain(entry.href);
    }
    expect(visibleEntries(user(permissions))).toHaveLength(
      container.querySelectorAll("a").length,
    );
  });
});
