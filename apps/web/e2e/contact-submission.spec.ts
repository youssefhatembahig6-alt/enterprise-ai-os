import { expect, test, type Page } from "@playwright/test";

/**
 * The contact form submits for real (spec 002 FR-023, FR-024a).
 *
 * **The test that did not exist.** Every other browser test of this form intercepts the
 * request with `page.route` — `performance.spec.ts` does it twice — so they assert the
 * form handles a response and never that it can obtain one. It could not: the browser
 * posted `application/json` cross-origin from `:3000` to `:8000`, which needs a CORS
 * preflight, and the API answers `OPTIONS /public/contact` with **405**. Verified
 * against the running stack before the fix.
 *
 * Nothing here may stub the network, which is the whole point of the file.
 *
 * **Deliberately frugal, and on one viewport.** FR-024d bounds accepted submissions at
 * five per address per hour, and every browser here shares one address. A generous
 * suite would exhaust the site's own rate limit and then fail with a 429 that looks
 * like a broken form — which is what the first draft did. One browser submission and
 * one server-side probe of that same submission, on one project: this checks a network
 * path, not a layout, so the three widths would be running the same assertion three
 * times at triple the cost.
 *
 * **What this file cannot claim.** That a row was written. There is no read path for
 * submissions (FR-023b), and the endpoint answers 202 for a stored row and a suppressed
 * duplicate alike — so no sequence of HTTP calls from here distinguishes them. Counting
 * rows needs the database, and that check lives in
 * `tests/e2e/test_contact_network_path.py`, which posts to this same site origin. An
 * earlier draft asserted it here by re-posting and expecting 202; it would have passed
 * against a form that stored nothing.
 */

test.describe.configure({ mode: "serial" });

const UNIQUE = () => `E2E ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

async function fillForm(page: Page, subject: string) {
  await page.goto("/contact");
  await page.getByLabel(/your name/i).fill("Amina Farouk");
  await page.getByLabel(/email address/i).fill("amina.farouk@example.com");
  await page.getByLabel(/subject/i).fill(subject);
  await page
    .getByLabel(/^message/i)
    .fill("We have twelve approval steps and no record of who signed what.");
}

test.describe("a real submission reaches the API", () => {
  // One viewport. This checks a network path rather than a layout, and every browser
  // shares one address against FR-024d's five-per-hour bound — running it at three
  // widths would triple the submissions to assert the same thing three times.
  // The empty destructure is required, not stylistic: Playwright resolves the first
  // argument's property names as fixtures, so naming it `_fixtures` makes it look for a
  // fixture by that name and fail. `{}` is how you say "no fixtures, just testInfo".
  // eslint-disable-next-line no-empty-pattern
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-1280",
      "network-path test; the contact rate limit is shared across projects",
    );
  });

  test("it posts, is accepted, and never addresses the API directly", async ({ page }) => {
    // Three assertions on one submission, because submissions are the scarce resource.
    const crossOrigin: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes(":8000")) crossOrigin.push(request.url());
    });

    const submission = page.waitForResponse(
      (r) => r.url().includes("/api/contact") && r.request().method() === "POST",
    );

    await fillForm(page, UNIQUE());
    await page.getByRole("button", { name: /send message/i }).click();

    const response = await submission;
    expect(
      response.status(),
      "the submission did not reach the API — this is the CORS failure the fix addresses",
    ).toBe(202);

    // The visitor is told, and told the truth.
    await expect(
      page.getByText(/thank you|we have your message|sent/i).first(),
    ).toBeVisible({ timeout: 15_000 });

    // The regression guard: if `submitContact` is pointed back at `apiBase()`, the
    // preflight fails and this catches it before a person does.
    expect(crossOrigin, "the browser addressed the API directly").toEqual([]);
  });

});

test.describe("the status page reads real data", () => {
  test("it renders dependency status obtained over the network", async ({ page }) => {
    // Same defect, second place, and it costs no submissions. `/status` fetched the
    // health endpoints cross-origin; a simple GET needs no preflight, but the response
    // is unreadable without `Access-Control-Allow-Origin`, which the API does not send.
    // `StatusPage.test.tsx` stubs `fetch`, so it never noticed.
    const health = page.waitForResponse((r) =>
      r.url().includes("/api/upstream/health/ready"),
    );

    await page.goto("/status");
    expect([200, 503]).toContain((await health).status());

    await expect(page.getByText(/postgres/i).first()).toBeVisible({ timeout: 15_000 });
  });
});
