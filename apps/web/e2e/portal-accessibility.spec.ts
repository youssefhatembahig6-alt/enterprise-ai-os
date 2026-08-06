import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PORTAL_PAGES } from "../lib/pages";

/**
 * WCAG 2.2 AA and keyboard access for the authenticated portal (spec 003 SC-010).
 *
 * SC-010: "Every portal surface renders ... verified by automated test", at the same
 * three viewport widths feature 002 verifies. Playwright's three projects supply the
 * widths; this file supplies the pages.
 *
 * **Separate from `accessibility.spec.ts` for one reason: these pages need a session.**
 * That file sweeps `PUBLIC_PAGES`, and every other browser sweep does the same — so
 * when the portal arrived, none of them reached it. A portal route added to the public
 * list would have been visited anonymously, redirected to the sign-in form, and the
 * sweep would have cheerfully reported "no violations" about the same login page three
 * times over.
 *
 * Automated checks cover only part of AA, which spec 002 FR-053 states outright. The
 * keyboard traversal below is the complement, not a duplicate.
 */

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const EMPLOYEE = "majid.alzaabi@niletech.example";
const MANAGER = "tarek.darwish@niletech.example";
const PASSWORD = "eaios-demo-local-only";

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/portal");
  await page.getByLabel("Work email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/portal\/home/);
}

test.describe("WCAG 2.2 AA", () => {
  test("the sign-in page has no violations", async ({ page }) => {
    // Anonymous, so it belongs here rather than in the authenticated sweep — but it is
    // a portal surface and SC-010 covers it.
    await page.goto("/portal");
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      results.violations.map((v) => `${v.id} (${v.impact}): ${v.help}`),
      "/portal violations",
    ).toEqual([]);
  });

  test("every authenticated portal page has no violations", async ({ page }) => {
    // A manager, so the team pages are reachable — an employee would be redirected
    // away from them and the sweep would silently cover fewer pages than it claims.
    await signIn(page, MANAGER);

    for (const path of PORTAL_PAGES) {
      await page.goto(path);
      const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(
        results.violations.map((v) => `${v.id} (${v.impact}): ${v.help}`),
        `${path} violations`,
      ).toEqual([]);
    }
  });

  test("a direct report's profile has no violations", async ({ page }) => {
    await signIn(page, MANAGER);
    await page.goto("/portal/team");

    const first = page.locator(".eaios-team-list a").first();
    if ((await first.count()) === 0) test.skip(true, "no direct reports in this dataset");
    await first.click();

    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });

  test("the sweep actually ran against a signed-in page", async ({ page }) => {
    // Anti-vacuity, and doubly needed here: axe reports zero violations on an empty
    // page, and it would also report zero on the sign-in form if the session had
    // silently failed and every navigation had redirected.
    await signIn(page, MANAGER);
    await page.goto("/portal/profile");

    await expect(page.getByRole("heading", { name: "My HR profile" })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(results.passes.length).toBeGreaterThan(5);
  });

  test("the page list it iterates is not empty", async () => {
    expect(PORTAL_PAGES.length).toBeGreaterThan(0);
  });
});

test.describe("keyboard access", () => {
  test("every portal page is reachable and has a focusable path", async ({ page }) => {
    await signIn(page, MANAGER);

    for (const path of PORTAL_PAGES) {
      await page.goto(path);

      // Something must be focusable, or a keyboard user cannot act on the page at all.
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => {
        const active = document.activeElement;
        return active && active !== document.body ? active.tagName : null;
      });
      expect(focused, `${path}: nothing focusable`).not.toBeNull();
    }
  });

  test("the portal navigation is traversable without a mouse", async ({ page }) => {
    await signIn(page, MANAGER);
    await page.goto("/portal/home");

    // Every navigation entry must be reachable by keyboard, or the role-aware
    // navigation is only aware of some of its users.
    const links = page.locator(".eaios-portal-nav a");
    const count = await links.count();
    expect(count, "no portal navigation links").toBeGreaterThan(0);

    for (let index = 0; index < count; index += 1) {
      await links.nth(index).focus();
      await expect(links.nth(index)).toBeFocused();
    }
  });

  test("focus is visible on the navigation", async ({ page }) => {
    // A focus ring removed by a reset stylesheet is the classic way a keyboard-usable
    // page becomes keyboard-unusable.
    await signIn(page, MANAGER);
    await page.goto("/portal/home");

    const link = page.locator(".eaios-portal-nav a").first();
    await link.focus();
    const outline = await link.evaluate((el) => {
      const style = getComputedStyle(el);
      return `${style.outlineStyle}|${style.outlineWidth}|${style.boxShadow}`;
    });
    expect(outline).not.toBe("none|0px|none");
  });
});

test.describe("responsive layout", () => {
  test("no portal page scrolls horizontally", async ({ page }) => {
    // Runs at all three project widths, so 360 is covered by the same assertion that
    // covers 1280 — which is where a fixed-width detail list would show up.
    await signIn(page, MANAGER);

    for (const path of PORTAL_PAGES) {
      await page.goto(path);
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflows, `${path} scrolls horizontally`).toBe(false);
    }
  });

  test("no element overflows the viewport", async ({ page }) => {
    await signIn(page, EMPLOYEE);
    await page.goto("/portal/profile");

    const wide = await page.evaluate(() => {
      const limit = document.documentElement.clientWidth + 1;
      return [...document.querySelectorAll("body *")]
        .filter((el) => el.getBoundingClientRect().right > limit)
        .map((el) => el.tagName + (el.className ? `.${String(el.className).split(" ")[0]}` : ""))
        .slice(0, 5);
    });
    expect(wide).toEqual([]);
  });
});
