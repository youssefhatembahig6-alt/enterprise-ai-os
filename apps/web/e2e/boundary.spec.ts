import { expect, test } from "@playwright/test";

import { PUBLIC_PAGES } from "../lib/pages";

/**
 * US6 — the portal entry exists and the anonymous boundary holds
 * (spec 002 FR-046, FR-048, FR-049a, FR-042, FR-043).
 *
 * The API side is covered by `tests/security/test_anonymous_refusal.py`. This is
 * the browser side: what a visitor actually reaches.
 *
 * **Updated by spec 003 FR-006 and FR-027.** This file used to assert that `/portal`
 * showed a "sign-in is not yet available" holding page and carried no input at all.
 * Feature 003 replaces that page's contents — at the same address, which FR-027
 * requires — with the real sign-in form.
 *
 * Spec 003's clarifications resolve the apparent conflict: FR-048 forbids **the public
 * site** requiring, accepting, or storing a visitor credential, and `/portal` is a
 * *non-content route* under spec 002's own FR-001a, outside that site. The eight
 * content pages stay credential-free.
 *
 * That distinction was never actually checked. The only test enforcing FR-048 was the
 * one on `/portal` — nothing verified the pages the requirement is really about. The
 * first test below is that missing check, and it is the one that would now catch a
 * login form appearing on the home page.
 */

test.describe("the public site accepts no credentials (FR-048)", () => {
  test("no content page carries a password or credential field", async ({ page }) => {
    // The requirement's actual subject: the eight public content pages. Driven from
    // the shared inventory, so a page added later is covered without anyone
    // remembering to add it here.
    for (const path of PUBLIC_PAGES) {
      await page.goto(path);
      await expect(page.locator('input[type="password"]'), path).toHaveCount(0);
      await expect(page.locator('input[autocomplete="current-password"]'), path).toHaveCount(0);
      await expect(page.locator('input[name*="password" i]'), path).toHaveCount(0);
    }
  });

  test("the inventory it iterates is not empty", async () => {
    // Without this, the sweep above passes by visiting nothing.
    expect(PUBLIC_PAGES.length).toBeGreaterThan(0);
  });
});

test.describe("the reserved portal address", () => {
  test("serves a designed page, not an error or a blank screen", async ({ page }) => {
    const response = await page.goto("/portal");
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/employee portal/i);
  });

  test("is the sign-in surface (spec 003 FR-006)", async ({ page }) => {
    // The address has not changed — FR-027 requires that, so every header link on the
    // public site keeps working. What changed is what it serves.
    await page.goto("/portal");
    await expect(page.getByLabel("Work email address")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("offers a route back into the public site", async ({ page }) => {
    // Someone who followed the header link by mistake needs a way out that is not the
    // browser's back button.
    await page.goto("/portal");
    await expect(page.getByRole("link", { name: /back to the public site/i })).toBeVisible();
  });

  test("reveals no portal structure beyond its own existence", async ({ page }) => {
    // Still true, and still worth checking: an anonymous visitor learns that a portal
    // exists and nothing about what is inside it.
    await page.goto("/portal");
    const body = (await page.locator("main").innerText()).toLowerCase();
    for (const term of ["dashboard", "admin", "audit log", "approvals", "my team"]) {
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
