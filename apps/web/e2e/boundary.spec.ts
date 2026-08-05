import { expect, test } from "@playwright/test";

/**
 * US6 — the portal entry exists and the anonymous boundary holds
 * (spec 002 FR-046, FR-048, FR-049a, FR-042, FR-043).
 *
 * The API side is covered by `tests/security/test_anonymous_refusal.py`. This is
 * the browser side: what a visitor actually reaches.
 */

test.describe("the reserved portal address", () => {
  test("serves a designed page, not an error or a blank screen", async ({ page }) => {
    const response = await page.goto("/portal");
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/employee portal/i);
    await expect(page.getByText(/sign-in is not yet available/i)).toBeVisible();
  });

  test("presents no credential field", async ({ page }) => {
    // FR-048 — the public site accepts no credentials at all. A stub login form
    // would satisfy the visible requirement and violate this one.
    await page.goto("/portal");
    await expect(page.locator("input")).toHaveCount(0);
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
  });

  test("offers a route back into the public site", async ({ page }) => {
    await page.goto("/portal");
    await expect(page.getByRole("link", { name: /back to the public site/i })).toBeVisible();
  });

  test("reveals no portal structure beyond its own existence", async ({ page }) => {
    await page.goto("/portal");
    const body = (await page.locator("main").innerText()).toLowerCase();
    for (const term of ["dashboard", "admin", "audit log", "approvals", "hr profile"]) {
      expect(body, `portal page mentions ${term}`).not.toContain(term);
    }
  });
});

test.describe("unknown addresses", () => {
  test("are reported as not found to crawlers", async ({ page }) => {
    // FR-043 — a 200 with an empty shell would let a crawler index a page that
    // does not exist.
    const response = await page.goto("/this-page-does-not-exist");
    expect(response?.status()).toBe(404);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/could not find/i);
  });

  test("a detail slug that does not exist resolves to not found", async ({ page }) => {
    const response = await page.goto("/careers/no-such-role-000000");
    expect(response?.status()).toBe(404);
  });

  test("the not-found page offers a way back", async ({ page }) => {
    await page.goto("/nope");
    await expect(page.getByRole("link", { name: /home page/i })).toBeVisible();
  });

  test("the not-found page discloses nothing internal", async ({ page }) => {
    await page.goto("/nope");
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const term of ["traceback", "postgres", "stack", "at /app/", "digest"]) {
      expect(body).not.toContain(term);
    }
  });
});

test.describe("crawler surface", () => {
  test("the sitemap lists public pages and excludes non-content routes", async ({
    request,
  }) => {
    const response = await request.get("/sitemap.xml");
    expect(response.status()).toBe(200);
    const xml = await response.text();

    expect(xml).toContain("/careers");
    expect(xml).toContain("/news");
    // FR-001a — neither is a public page.
    expect(xml).not.toContain("/portal");
    expect(xml).not.toContain("/status");
  });

  test("robots points at the sitemap", async ({ request }) => {
    const body = await (await request.get("/robots.txt")).text();
    expect(body.toLowerCase()).toContain("sitemap");
  });
});
