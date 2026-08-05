import { expect, test } from "@playwright/test";

import { NON_CONTENT_ROUTES, PUBLIC_PAGES } from "./pages";

/**
 * FR-032, SC-004 — verified at 360, 768, and 1280 (the Playwright projects), with
 * no horizontal page scroll at any width from 320px upward.
 *
 * The three widths are where layout is *asserted*; they are not the only widths
 * that must work, which is why the last test samples between them.
 */

const ALL_ROUTES = [...PUBLIC_PAGES, ...NON_CONTENT_ROUTES];

for (const path of ALL_ROUTES) {
  test(`${path} does not scroll horizontally`, async ({ page }) => {
    await page.goto(path);
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(
      scrollWidth,
      `${path} overflows by ${scrollWidth - clientWidth}px`,
    ).toBeLessThanOrEqual(clientWidth);
  });
}

test("no element overflows the viewport", async ({ page }) => {
  await page.goto("/careers");
  const overflowing = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll("body *")]
      .filter((el) => el.getBoundingClientRect().right > width + 1)
      .map((el) => `${el.tagName}.${el.className}`)
      .slice(0, 5);
  });
  expect(overflowing).toEqual([]);
});

test("the layout holds at widths between the verified ones", async ({ page }) => {
  // FR-032 forbids horizontal scroll at *any* width from 320px, so sampling only
  // the three asserted widths would leave the gaps untested — which is exactly
  // where the 768px navigation overflow was found.
  for (const width of [320, 480, 600, 900, 1100, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflows, `overflow at ${width}px`).toBe(false);
  }
});

test("interactive elements meet the minimum target size", async ({ page }) => {
  // WCAG 2.2 AA 2.5.8. Absent from the responsive requirements, but the
  // conformance commitment in FR-053 brings it in (checklists/responsive.md CHK005).
  await page.goto("/");
  const tooSmall = await page.evaluate(() => {
    const MIN = 24;
    // WCAG 2.5.8 exempts targets that sit inline within a block of text — a link
    // in a sentence is sized by its type, and enlarging it would break the
    // paragraph. Standalone controls have no such excuse, so the check is scoped
    // to buttons, form controls, and links styled as controls.
    const selector = "button, input, select, textarea, .eaios-button, .eaios-nav__link";
    return [...document.querySelectorAll(selector)]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && (r.width < MIN || r.height < MIN);
      })
      .map((el) => `${el.tagName}: ${el.textContent?.trim().slice(0, 24)}`)
      .slice(0, 5);
  });
  expect(tooSmall).toEqual([]);
});
