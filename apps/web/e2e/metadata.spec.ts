import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { NON_CONTENT_ROUTES, PUBLIC_PAGES } from "./pages";

/**
 * Search-engine metadata (spec 002 FR-039 – FR-043, SC-011).
 *
 * The strongest assertion here is uniqueness. FR-039 forbids two distinct pages
 * sharing generic placeholder metadata, and a template falling back to a default
 * would pass a per-page presence check while failing the requirement.
 */

async function meta(page: Page, name: string): Promise<string | null> {
  return page
    .locator(`meta[name="${name}"], meta[property="${name}"]`)
    .first()
    .getAttribute("content");
}

test("every public page has a title and description", async ({ page }) => {
  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    await expect(page, `${path} title`).toHaveTitle(/.{10,}/);
    expect(await meta(page, "description"), `${path} description`).toBeTruthy();
  }
});

test("no two pages share a title or a description", async ({ page }) => {
  const titles: string[] = [];
  const descriptions: string[] = [];

  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    titles.push(await page.title());
    descriptions.push((await meta(page, "description")) ?? "");
  }

  expect(new Set(titles).size, `duplicate titles: ${titles.join(" | ")}`).toBe(titles.length);
  expect(new Set(descriptions).size).toBe(descriptions.length);
});

test("every page declares a canonical address", async ({ page }) => {
  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
    expect(canonical, `${path} canonical`).toContain(path);
  }
});

test("every page carries social-preview metadata", async ({ page }) => {
  for (const path of PUBLIC_PAGES) {
    await page.goto(path);
    expect(await meta(page, "og:title"), `${path} og:title`).toBeTruthy();
    expect(await meta(page, "og:description"), `${path} og:description`).toBeTruthy();
  }
});

test("detail pages derive metadata from the record they show", async ({ page }) => {
  // FR-041 — a detail page inheriting the section's generic description would
  // satisfy "has a description" and defeat the point.
  await page.goto("/news");

  // Both reads are scoped to the *same* card. Taking `.first()` of the titles and
  // `.first()` of the links independently assumed the two lists stay aligned, and
  // this test failed once in a full parallel run and passed on its own — the shape
  // of a race, not of a broken page. Reading one card cannot drift.
  const card = page.locator(".eaios-card").first();
  await card.waitFor();
  const headline = (await card.locator(".eaios-card__title").textContent())?.trim();
  const href = await card.getByRole("link", { name: /read the announcement/i }).getAttribute("href");

  expect(headline, "no headline found on the first card").toBeTruthy();
  expect(href, "no article link found on the first card").toBeTruthy();

  await page.goto(href!);
  expect(await page.title()).toContain(headline!);
});

test("non-content routes are excluded from indexing", async ({ page }) => {
  for (const path of NON_CONTENT_ROUTES) {
    await page.goto(path);
    expect(await meta(page, "robots"), `${path} should not be indexed`).toContain("noindex");
  }
});

test.describe("the sitemap is built from the shared route list", () => {
  /**
   * FR-042 and FR-001a. Asserted against what the server actually serves, because
   * the failure this guards against is a build that renders a stale list: the
   * module can be correct while the deployed sitemap is not.
   */
  test("lists every public page and neither non-content route", async ({ request }) => {
    const body = await (await request.get("/sitemap.xml")).text();

    for (const path of PUBLIC_PAGES) {
      const suffix = path === "/" ? "/" : path;
      expect(body, `sitemap omits ${path}`).toContain(`${suffix}</loc>`);
    }
    for (const route of NON_CONTENT_ROUTES) {
      expect(body, `sitemap exposes ${route}`).not.toContain(`${route}</loc>`);
    }
  });

  test("the sitemap check reads a real document", async ({ request }) => {
    // An empty or error response would satisfy the "does not contain" half above.
    const response = await request.get("/sitemap.xml");
    expect(response.status()).toBe(200);
    expect((await response.text()).length).toBeGreaterThan(200);
  });
});
