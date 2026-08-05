import { expect, test } from "@playwright/test";

/** US2, US3, US5 — careers, news, and leadership. */

test.describe("careers", () => {
  test("lists open roles with team and location", async ({ page }) => {
    await page.goto("/careers");
    await expect(page.getByRole("heading", { level: 1, name: "Careers" })).toBeVisible();
    expect(await page.locator(".eaios-card").count()).toBeGreaterThan(0);
  });

  test("a filter narrows the list and stays in the address", async ({ page }) => {
    await page.goto("/careers");
    const before = await page.locator(".eaios-card").count();

    await page.selectOption("#office", { index: 1 });
    await page.getByRole("button", { name: /apply filters/i }).click();

    await expect(page).toHaveURL(/office=/);
    const after = await page.locator(".eaios-card").count();
    expect(after).toBeLessThanOrEqual(before);
    await expect(page.getByRole("link", { name: /clear filters/i })).toBeVisible();
  });

  test("a filter matching nothing explains itself and offers a way out", async ({ page }) => {
    await page.goto("/careers?office=Alexandria&department=Executive%20Management");

    // Diagnostic wrapper, not a widened timeout. This assertion fails roughly one
    // full-suite run in four, only with all three viewport projects running at once
    // and never in isolation — the signature of contention rather than a broken
    // page. Two earlier flakes in this suite looked identical and had different
    // causes (one a stale card index, one a mobile-menu race), and both were found
    // by printing what the page actually showed. Guessing at a fix without that
    // would be guessing.
    try {
      await expect(page.getByText(/no roles match that filter/i)).toBeVisible();
    } catch (failure) {
      const shown = (await page.locator("main").innerText()).slice(0, 300);
      throw new Error(`empty filter state never appeared. Page showed:
${shown}

${failure}`);
    }
    // Two "Clear filters" links exist by design — one in the filter form, one in
    // the empty state — so the locator is scoped to the region under test.
    await expect(
      page.getByRole("region", { name: /matching roles/i }).getByRole("link", {
        name: /clear filters/i,
      }),
    ).toBeVisible();
  });

  test("a role opens to its full description", async ({ page }) => {
    await page.goto("/careers");
    await page.getByRole("link", { name: /see the role/i }).first().click();
    await expect(page).toHaveURL(/\/careers\/.+/);
    await expect(page.getByRole("heading", { name: /about the role/i })).toBeVisible();
  });
});

test.describe("news", () => {
  test("lists announcements newest first", async ({ page }) => {
    await page.goto("/news");
    const dates = await page.locator("time").allTextContents();
    expect(dates.length).toBeGreaterThan(0);
    expect([...dates]).toEqual([...dates].sort().reverse());
  });

  test("an article opens with its headline and date", async ({ page }) => {
    await page.goto("/news");
    await page.getByRole("link", { name: /read the announcement/i }).first().click();
    await expect(page).toHaveURL(/\/news\/.+/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("time")).toBeVisible();
  });
});

test.describe("leadership", () => {
  test("shows profiles with a title and biography", async ({ page }) => {
    await page.goto("/leadership");
    const cards = page.locator(".eaios-card");
    expect(await cards.count()).toBeGreaterThan(0);
    await expect(cards.first()).toContainText(/./);
  });

  test("exposes no internal identifier", async ({ page }) => {
    // FR-013 — name, public title, biography, and nothing else about the person.
    //
    // Scoped to the leadership region, not the whole document. The footer carries
    // `hello@niletech.example`, the general enquiry address FR-018 requires — a
    // page-wide email assertion flags that and fails a correct page.
    await page.goto("/leadership");
    const region = page.getByRole("region", { name: /leadership team/i });
    const html = await region.innerHTML();
    expect(html).not.toContain("user_id");
    expect(html).not.toMatch(/@/);
  });
});

test.describe("every news item is reachable (FR-016)", () => {
  /**
   * `app/news/page.tsx` calls `getNews(50)` against a dataset that currently holds
   * eleven items, so the requirement is met by volume rather than by design: there
   * is no pagination, and nothing compared what the page renders to what the API
   * says exists. The day the dataset crosses the ceiling, items would vanish from
   * the site and every test would still pass.
   *
   * This makes the ceiling announce itself. It does not add pagination — that is a
   * design decision for whoever crosses the threshold, and this failing is how they
   * find out they have.
   */
  test("the page renders as many items as the API reports", async ({ page, request }) => {
    // Absolute, because Playwright's `request` fixture inherits `baseURL` — the
    // *site*. A relative "/public/news" reaches Next, which answers with its 404
    // document, and the failure reads as malformed JSON rather than as a wrong host.
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const { total } = await (await request.get(`${apiBase}/public/news?limit=1&offset=0`)).json();

    await page.goto("/news");
    const rendered = await page.locator(".eaios-card").count();

    expect(total, "the API reports no news at all").toBeGreaterThan(0);
    expect(rendered, `page shows ${rendered} of ${total} announcements`).toBe(total);
  });

  test("each rendered item links to its own article", async ({ page }) => {
    // Reachability is the requirement, not presence: a card with no link is listed
    // and unreachable, which is the failure FR-016 is about.
    await page.goto("/news");
    const cards = page.locator(".eaios-card");
    const count = await cards.count();

    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const href = await cards
        .nth(index)
        .getByRole("link", { name: /read the announcement/i })
        .getAttribute("href");
      expect(href, `card ${index} carries no article link`).toMatch(/^\/news\/.+/);
    }
  });

  test("the last item in the list opens", async ({ page }) => {
    // The first card is what every other test opens. If a ceiling ever truncated
    // the list, the tail is where it would show.
    await page.goto("/news");
    const last = page.locator(".eaios-card").last();
    const headline = (await last.locator(".eaios-card__title").textContent())?.trim();
    const href = await last
      .getByRole("link", { name: /read the announcement/i })
      .getAttribute("href");

    const response = await page.goto(href!);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(headline!);
  });
});
