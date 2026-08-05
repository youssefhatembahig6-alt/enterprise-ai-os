/**
 * The Server Error page discloses nothing (spec 002 FR-029, SC-013, FR-027).
 *
 * SC-013 names two pages — Not Found **and** Server Error — and only the first was
 * checked: `e2e/boundary.spec.ts` covers not-found, while nothing anywhere rendered
 * `app/error.tsx`. It is a Next error boundary, so it receives the `Error` object as
 * a prop, and it deliberately renders none of it. That was correct and entirely
 * unverified: a `{error.message}` added during a debugging session would have shipped
 * past every test in the repository.
 *
 * The error used below carries the four things a real failure leaks — a driver name,
 * an internal hostname, a port, and a stack frame naming a source path.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorPage from "../app/error";

const LEAKY = (() => {
  const error = new Error(
    "psycopg.OperationalError: connection to server at postgres.internal (10.0.3.14), " +
      'port 5432 failed — SELECT * FROM users WHERE company_id = $1',
  );
  error.stack =
    "Error: psycopg.OperationalError\n" +
    "    at getJson (/app/apps/web/lib/api.ts:78:17)\n" +
    "    at ServicesPage (/app/apps/web/app/services/page.tsx:28:9)";
  // Next attaches this to server errors; it identifies the failure in the logs and
  // means nothing to a visitor.
  (error as Error & { digest?: string }).digest = "3064285774";
  return error;
})();

/** Every fragment that must not reach the document. */
const DISCLOSURES = [
  "psycopg",
  "OperationalError",
  "postgres.internal",
  "10.0.3.14",
  "5432",
  "SELECT",
  "company_id",
  "/app/apps/web/lib/api.ts",
  "3064285774",
];

describe("the server error page", () => {
  it("renders nothing from the error it was given", () => {
    const { container } = render(<ErrorPage error={LEAKY} reset={vi.fn()} />);
    const text = container.textContent ?? "";

    for (const fragment of DISCLOSURES) {
      expect(text, `the page disclosed ${fragment}`).not.toContain(fragment);
    }
  });

  it("explains that something went wrong", () => {
    // FR-029. The other half of the requirement: silence is not the goal, a page
    // that renders nothing at all would pass every assertion above.
    render(<ErrorPage error={LEAKY} reset={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 }).textContent?.length).toBeGreaterThan(10);
  });

  it("offers a route onward", () => {
    render(<ErrorPage error={LEAKY} reset={vi.fn()} />);
    expect(screen.getByRole("link", { name: /home/i })).toBeInTheDocument();
  });

  it("offers a manual retry, and does not retry by itself", () => {
    // FR-027 — visitor-initiated. `reset` must not be called during render, or a
    // failing dependency gets a retry storm from every visitor who lands here.
    const reset = vi.fn();
    render(<ErrorPage error={LEAKY} reset={reset} />);

    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(reset).not.toHaveBeenCalled();
  });

  it("blames itself rather than the visitor", () => {
    render(<ErrorPage error={LEAKY} reset={vi.fn()} />);
    expect(document.body.textContent?.toLowerCase()).toContain("ours");
  });
});

describe("the disclosure check can fail", () => {
  /**
   * Without this, the assertions above would be satisfied by a component that
   * rendered an empty div — "does not contain" is trivially true of nothing. These
   * confirm the probe is looking at real text and that the fixture really does carry
   * the fragments being searched for.
   */
  it("the fixture carries every fragment the page must suppress", () => {
    const source = `${LEAKY.message} ${LEAKY.stack} ${(LEAKY as Error & { digest?: string }).digest}`;
    for (const fragment of DISCLOSURES) {
      expect(source, `the fixture does not contain ${fragment}`).toContain(fragment);
    }
  });

  it("the same search finds a fragment when one is present", () => {
    const { container } = render(
      <div>
        connection to server at postgres.internal (10.0.3.14) failed
      </div>,
    );
    expect(container.textContent).toContain("10.0.3.14");
  });

  it("the page under test renders visible content", () => {
    const { container } = render(<ErrorPage error={LEAKY} reset={vi.fn()} />);
    expect((container.textContent ?? "").trim().length).toBeGreaterThan(40);
  });
});
