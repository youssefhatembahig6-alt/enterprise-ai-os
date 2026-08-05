import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { PUBLIC_PAGES } from "./pages";

/**
 * WCAG 2.2 Level AA (spec 002 FR-053, SC-005).
 *
 * Automated checks cover only part of AA, which FR-053 states outright and SC-005
 * was amended to reflect — a clean run here does **not** establish conformance on
 * its own. `keyboard.spec.ts` covers the complement, and SC-005 requires both.
 */

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

for (const path of PUBLIC_PAGES) {
  test(`${path} has no accessibility violations`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();

    // Named in the failure so the report says which rule, on how many elements.
    const summary = results.violations.map(
      (v) => `${v.id} (${v.impact}) on ${v.nodes.length} node(s): ${v.help}`,
    );
    expect(summary, `${path} violations`).toEqual([]);
  });
}

test("detail pages have no accessibility violations", async ({ page }) => {
  // Resolved from a real slug rather than hard-coded, so the sweep follows the
  // dataset instead of a fixture that could go stale.
  await page.goto("/careers");
  const href = await page
    .getByRole("link", { name: /see the role/i })
    .first()
    .getAttribute("href");
  expect(href, "no vacancy to open").toBeTruthy();

  await page.goto(href!);
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(results.violations.map((v) => v.id)).toEqual([]);
});

test("the not-found page has no accessibility violations", async ({ page }) => {
  await page.goto("/this-does-not-exist");
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(results.violations.map((v) => v.id)).toEqual([]);
});

test("the sweep actually ran against real content", async ({ page }) => {
  // Anti-vacuity: axe reports zero violations on an empty page too.
  await page.goto("/services");
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(results.passes.length).toBeGreaterThan(5);
});
