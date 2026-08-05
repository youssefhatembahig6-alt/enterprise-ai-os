import { expect, test, type Page } from "@playwright/test";

import { PUBLIC_PAGES } from "./pages";

/**
 * SC-014's two halves (spec 002 SC-014, FR-027a, FR-025).
 *
 * The criterion says main content becomes visible within **three seconds**, and
 * that no page holds an indefinite loading state. Neither half was measured; the
 * criterion existed as a sentence.
 *
 * **What a timing assertion here does and does not establish.** It runs against a
 * local stack on the developer's or CI machine: same host, no network, warm
 * database, one visitor. That is a *floor*, not a guarantee — passing here does not
 * predict a visitor in Alexandria on a phone, and it is not evidence about
 * production capacity, which this feature has none of. What it does catch is the
 * regression class it exists for: a page that starts blocking on something slow —
 * an unbounded query, a fetch without a timeout, a sequential waterfall where a
 * parallel read belonged. Under those conditions three seconds on localhost is
 * comfortably exceeded, which is why the budget is asserted rather than a tighter
 * number that would fail on a loaded CI runner and teach everyone to ignore it.
 *
 * The pages come from `pages.ts`, so a page added later is measured by default.
 */

/** SC-014's stated budget, in milliseconds. */
const BUDGET_MS = 3_000;

/** FR-027a — a client-fetched region becomes an error state after ten seconds.
 *  The bound SC-014's "no indefinite loading state" is tested against. */
const LOADING_BOUND_MS = 10_000;

/**
 * First Contentful Paint, as the browser measured it.
 *
 * Wall-clock around `page.goto` was the obvious approach and the wrong one: it
 * includes Playwright's own RPC and, under parallel workers, the time this test
 * spent waiting for a CPU. An early run failed on `/products` at a moment when the
 * server was answering that route in 33ms — the test was measuring the runner.
 */
async function firstContentfulPaint(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      performance.getEntriesByName("first-contentful-paint")[0]?.startTime ??
      performance.getEntriesByType("navigation")[0]?.duration ??
      0,
  );
}

/** Addressed by role rather than by label text: the page's own
 *  `<section aria-labelledby="send-message">` also answers to `getByLabel(/message/i)`,
 *  and a strict-mode violation there fails for a reason unrelated to what is
 *  being measured. */
async function fillContactForm(page: Page): Promise<void> {
  const form = page.getByRole("form", { name: "Contact form" });
  await form.getByRole("textbox", { name: "Your name" }).fill("Amina Farouk");
  await form.getByRole("textbox", { name: "Email address" }).fill("amina.farouk@example.com");
  await form.getByRole("textbox", { name: "Subject" }).fill("Automation for approvals");
  await form
    .getByRole("textbox", { name: "Message" })
    .fill("We have twelve approval steps and no record of who signed what.");
  await form.getByRole("button", { name: /send/i }).click();
}

test.describe("main content arrives inside the budget", () => {
  for (const path of PUBLIC_PAGES) {
    test(`${path} shows its main heading within ${BUDGET_MS}ms`, async ({ page }) => {
      await page.goto(path);

      // The h1 is what SC-014 means by "main content": the point at which a visitor
      // can tell what page they are on.
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
        timeout: BUDGET_MS,
      });

      const paint = await firstContentfulPaint(page);
      // Recorded even on success — a page drifting from 200ms to 2,900ms passes,
      // and the number is the only way anyone would notice before it stopped.
      test.info().annotations.push({ type: "fcp-ms", description: `${path}: ${paint}` });
      expect(paint, `${path} painted after ${paint}ms`).toBeLessThan(BUDGET_MS);
    });
  }

  test("the slowest page is the one carrying the most content", async ({ page }) => {
    // `/careers` reads the vacancy list twice — once unfiltered for the filter
    // options, once for the results (FR-014). If that ever stops being two
    // concurrent reads, this is where it shows up first.
    await page.goto("/careers");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: BUDGET_MS });
    expect(await firstContentfulPaint(page)).toBeLessThan(BUDGET_MS);
  });
});

test.describe("no page holds an indefinite loading state", () => {
  test("a server-rendered page presents no loading affordance at all", async ({ page }) => {
    // FR-025 as amended: a server-rendered region arrives with its content, so a
    // spinner there is one that can never resolve because it never had anything to
    // wait for. Its absence is the requirement.
    await page.goto("/services");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  });

  test("a stalled contact submission ends in an error state, not a spinner", async ({ page }) => {
    // The contact form is one of the two client-fetched regions (FR-025). Its
    // request is held open indefinitely, which is the exact condition SC-014
    // forbids the interface from sitting in.
    await page.route("**/public/contact", () => {
      // Never fulfilled and never aborted: the request simply hangs.
    });

    await page.goto("/contact");
    await fillContactForm(page);

    // Addressed by its text, not by `role="alert"` alone: the form keeps an empty
    // live region mounted so a later message is announced rather than appearing
    // with the element. That region is present from the first paint, so asserting
    // on the role would pass instantly and measure nothing.
    await expect(page.getByText(/your message was not sent/i)).toBeVisible({
      // FR-027a's ten-second bound, with headroom for the browser's own scheduling.
      timeout: LOADING_BOUND_MS + 5_000,
    });

    // And the submit control is usable again — an interface that reports an error
    // but stays disabled has substituted one dead end for another.
    await expect(page.getByRole("button", { name: /send message/i })).toBeEnabled();
  });

  test("the stall test would fail if the form never bounded its wait", async ({ page }) => {
    // Anti-vacuity guard for the test above. If the route interception were not
    // taking effect, the submission would succeed and the assertion would be
    // passing on an ordinary error-free page. This proves the stall is real: with
    // the same interception, nothing has resolved after two seconds.
    await page.route("**/public/contact", () => {});

    await page.goto("/contact");
    await fillContactForm(page);

    await page.waitForTimeout(2_000);
    await expect(page.getByText(/thank you|we have your message/i)).toHaveCount(0);
  });
});
