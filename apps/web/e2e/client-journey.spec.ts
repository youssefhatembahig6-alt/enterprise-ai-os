import { expect, test, type Page } from "@playwright/test";

/**
 * US1 — a prospective client evaluates NileTech.
 *
 * Runs at 360, 768, and 1280 (the widths FR-032 verifies) because the Playwright
 * config declares them as projects. A test that opted into widths would be a test
 * someone forgets to opt in.
 *
 * Needs a seeded stack: `make up && make seed`.
 */

const PAGES = [
  { path: "/", heading: /business automation/i },
  { path: "/about", heading: /about niletech/i },
  { path: "/services", heading: /^services$/i },
  { path: "/products", heading: /^products$/i },
];

test.describe("the client journey", () => {
  test("every page in the journey responds and has one h1", async ({ page }) => {
    for (const target of PAGES) {
      const response = await page.goto(target.path);
      expect(response?.status(), `${target.path} status`).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(target.heading);
    }
  });

  test("navigation reaches every page from any page", async ({ page }) => {
    await page.goto("/products");
    // The mobile menu has to be opened before its links are reachable.
    const toggle = page.getByRole("button", { name: /menu/i });
    if (await toggle.isVisible()) await toggle.click();

    // Scoped to the primary nav: the footer also links to Services, and an
    // unscoped locator matches both.
    await page.getByLabel("Primary").getByRole("link", { name: "Services" }).click();
    await expect(page).toHaveURL(/\/services$/);
    await expect(page.getByRole("heading", { level: 1, name: "Services" })).toBeVisible();
  });

  test("the current page is marked for assistive technology", async ({ page }) => {
    await page.goto("/services");
    const toggle = page.getByRole("button", { name: /menu/i });
    if (await toggle.isVisible()) await toggle.click();
    await expect(page.locator('a[aria-current="page"]')).toHaveText("Services");
  });

  // Named for both pages and visiting only `/services` until this loop replaced it.
  // Nothing was actually unchecked — `/products` is swept by the accessibility,
  // metadata, responsive, performance, and state-coverage suites, which all iterate
  // the shared page list — but a test whose name claims coverage it does not provide
  // is the same defect as the `// Three independent regions (FR-005)` comment that
  // let a missing home-page section survive four convergence runs. A reader trusts
  // both.
  for (const path of ["/services", "/products"]) {
    test(`${path} shows real generated content`, async ({ page }) => {
      await page.goto(path);
      const cards = page.locator(".eaios-card");
      await expect(cards.first()).toBeVisible();
      expect(await cards.count()).toBeGreaterThan(0);

      // Visible text only. `textContent("body")` also returns Next's serialised
      // RSC payload from its <script> tags, which legitimately contains the string
      // "$undefined" — an assertion against it fails on a correct page.
      const visible = await page.locator("main").innerText();
      expect(visible.toLowerCase()).not.toContain("lorem ipsum");
      expect(visible).not.toContain("undefined");
    });
  }

  test("the page body never scrolls horizontally", async ({ page }) => {
    for (const target of PAGES) {
      await page.goto(target.path);
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(overflows, `${target.path} scrolls horizontally`).toBe(false);
    }
  });

  test("the skip link is the first thing a keyboard user reaches", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveText(/skip to content/i);
  });

  test("the portal entry is present on every page", async ({ page }) => {
    for (const target of PAGES) {
      await page.goto(target.path);
      await expect(
        page.getByRole("link", { name: /employee portal/i }),
      ).toBeVisible();
    }
  });
});

test.describe("SC-003 — a role is three interactions from the root", () => {
  /**
   * The criterion puts a number on the path from the **site root** to the full
   * description of a specific open role. Nothing measured it: the nearest test
   * (`content-journeys.spec.ts`, "a role opens to its full description") starts at
   * `/careers`, which skips the interaction the criterion is mostly about, and
   * counts nothing.
   *
   * The path is two clicks today, so this passes with room to spare. That is the
   * point of writing the budget down rather than leaving it as a property of the
   * current layout: it would stop passing if Careers left the primary navigation,
   * if a filter had to be applied before roles appeared, or if the home page's
   * open-roles block lost its link.
   */
  const BUDGET = 3;

  /**
   * Confirms the role description arrived, and says what did arrive when it did not.
   *
   * The plain `toBeVisible()` here failed roughly one run in three — only ever with
   * all three viewport projects running at once, never in isolation. Both halves are
   * deliberate. The longer timeout covers a *client-side* navigation (`next/link`
   * fetches the RSC payload) on a machine running eighteen browsers, which the 5s
   * default does not; and the message reports the page's actual content, so if this
   * ever fails again it says whether the visitor got an error state or merely a slow
   * one, instead of "element not visible".
   */
  async function expectRoleDescription(page: Page) {
    const heading = page.getByRole("heading", { name: /about the role/i });
    try {
      await expect(heading).toBeVisible({ timeout: 15_000 });
    } catch (failure) {
      const shown = (await page.locator("main").innerText()).slice(0, 300);
      throw new Error(`role description never appeared. Page showed:
${shown}

${failure}`);
    }
  }

  test("via the primary navigation", async ({ page }) => {
    let interactions = 0;

    await page.goto("/");

    // Below 1024px the navigation is collapsed behind a toggle (FR-037), so opening
    // it is an interaction and has to be counted as one. Writing this test revealed
    // that: at 360px and 768px the path costs the full three, meeting SC-003 with no
    // headroom at all, while the desktop path costs two. A count that quietly
    // skipped the toggle would have reported the desktop number at every width.
    const toggle = page.getByRole("button", { name: /menu/i });
    if (await toggle.isVisible()) {
      await toggle.click();
      interactions += 1;
    }

    await page.getByRole("navigation").getByRole("link", { name: "Careers" }).click();
    interactions += 1;

    // Wait for the careers page before clicking into it. Not padding: the mobile
    // menu closes on a pathname change (`Navigation.tsx` line 27), so clicking the
    // role link immediately raced that transition and landed while the overlay was
    // still up. The failure diagnostic above reported the page as `/careers` with
    // the filter UI showing — which is what told me it was a race and not a slow
    // render. A visitor sees the list before choosing from it, so this is also the
    // more faithful journey.
    await expect(page).toHaveURL(/\/careers$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Careers");

    await page.getByRole("link", { name: /see the role/i }).first().click();
    interactions += 1;

    await expect(page).toHaveURL(/\/careers\/.+/);
    await expectRoleDescription(page);
    expect(interactions, `took ${interactions} interactions`).toBeLessThanOrEqual(BUDGET);
  });

  test("via the home page's open-roles summary", async ({ page }) => {
    // The shorter path, and the one FR-005's summary blocks exist to provide. A
    // visitor who never touches the navigation should still get there.
    let interactions = 0;

    await page.goto("/");

    const roles = page.locator("section", { has: page.getByRole("heading", { name: "Open roles" }) });
    await roles.getByRole("link", { name: /see the role/i }).first().click();
    interactions += 1;

    await expect(page).toHaveURL(/\/careers\/.+/);
    await expectRoleDescription(page);
    expect(interactions).toBeLessThanOrEqual(BUDGET);
  });

  test("the counted path is real, not a redirect", async ({ page }) => {
    // Guards both budgets above: if the root already redirected to a role, or the
    // links were inert, the counts would be trivially small and meaningless.
    const landing = await page.goto("/");
    expect(landing?.status()).toBe(200);
    expect(new URL(page.url()).pathname).toBe("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Business automation that leaves a record",
    );
  });
});
