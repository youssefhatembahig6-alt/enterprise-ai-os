import { expect, test } from "@playwright/test";

import { PUBLIC_PAGES } from "./pages";

/**
 * The keyboard-only pass FR-053 requires alongside the automated checks.
 *
 * These are the failures axe does not reliably detect — focus traps, invisible
 * focus, unreachable controls, and focus that does not return on dismissal. They
 * account for most real keyboard problems, which is why FR-053 names them.
 */

test.describe("keyboard operation", () => {
  for (const path of PUBLIC_PAGES) {
    test(`${path} puts the skip link first`, async ({ page }) => {
      await page.goto(path);
      await page.keyboard.press("Tab");
      await expect(page.locator(":focus")).toHaveText(/skip to content/i);
    });
  }

  test("every form control is reachable by Tab alone", async ({ page }) => {
    await page.goto("/contact");

    const reachable = new Set<string>();
    for (let i = 0; i < 40; i += 1) {
      await page.keyboard.press("Tab");
      const id = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        return `${el.tagName}:${el.id || el.textContent?.trim().slice(0, 20) || ""}`;
      });
      if (id) reachable.add(id);
    }

    const joined = [...reachable].join(" ");
    expect(joined).toMatch(/INPUT/);
    expect(joined).toMatch(/TEXTAREA/);
    expect(joined).toMatch(/BUTTON/);
  });

  test("focus is visible wherever it lands", async ({ page }) => {
    await page.goto("/");
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press("Tab");
      const visible = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return true;
        const style = getComputedStyle(el);
        // The token layer applies a 3px outline on :focus-visible, so an element
        // with neither outline nor shadow has opted out of the one focus style
        // the site defines.
        return style.outlineStyle !== "none" || style.boxShadow !== "none";
      });
      expect(visible).toBe(true);
    }
  });
});

test.describe("mobile navigation", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 1024, "menu is not collapsed");

  test("dismisses on Escape and returns focus to the toggle", async ({ page }) => {
    // FR-037 — "traps focus only while open" is meaningless unless dismissal puts
    // focus somewhere sensible. Without this the next Tab restarts from the top.
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /menu/i });

    await toggle.click();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
    await expect(toggle).toBeFocused();
  });

  test("reports its expanded state", async ({ page }) => {
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /menu/i });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
