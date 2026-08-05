/**
 * The three states a server-rendered content region can be in
 * (spec 002 FR-025 as amended, FR-026, FR-027, FR-030).
 *
 * `Section` is an async server component, so it is awaited and the resolved
 * element rendered — Testing Library cannot render a promise directly.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Section } from "../components/Section";

async function renderSection(load: () => Promise<{ name: string }[]>) {
  const element = await Section<{ name: string }>({
    title: "Things",
    id: "things",
    load,
    empty: { title: "Nothing here", body: "There is nothing to show yet." },
    children: (items) => items.map((item) => <p key={item.name}>{item.name}</p>),
  });
  render(element);
}

describe("populated state", () => {
  it("renders every item it was given", async () => {
    await renderSection(async () => [{ name: "Alpha" }, { name: "Beta" }]);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("labels the region with its heading", async () => {
    await renderSection(async () => [{ name: "Alpha" }]);
    expect(screen.getByRole("region", { name: "Things" })).toBeInTheDocument();
  });
});

describe("empty state", () => {
  it("explains what is absent rather than showing a blank region", async () => {
    await renderSection(async () => []);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("There is nothing to show yet.")).toBeInTheDocument();
  });

  it("offers a next action", async () => {
    await renderSection(async () => []);
    expect(screen.getByRole("link", { name: /get in touch/i })).toBeInTheDocument();
  });

  it("announces itself to assistive technology", async () => {
    await renderSection(async () => []);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("error state", () => {
  it("reports failure instead of pretending the section is empty", async () => {
    await renderSection(async () => {
      throw new Error("boom");
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Nothing here")).not.toBeInTheDocument();
  });

  it("discloses nothing about the cause", async () => {
    await renderSection(async () => {
      throw new Error("connection to postgresql://user:pw@db refused");
    });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).not.toContain("postgresql");
    expect(alert.textContent).not.toContain("refused");
  });

  it("keeps the section heading so the page structure survives", async () => {
    await renderSection(async () => {
      throw new Error("boom");
    });
    // FR-030: the failure is contained to this region, not replacing the page.
    expect(screen.getByRole("heading", { name: "Things" })).toBeInTheDocument();
  });
});

describe("the states are distinguishable", () => {
  it("empty and error do not render the same thing", async () => {
    await renderSection(async () => []);
    const empty = document.body.innerHTML;
    document.body.innerHTML = "";
    await renderSection(async () => {
      throw new Error("boom");
    });
    expect(document.body.innerHTML).not.toEqual(empty);
  });
});
