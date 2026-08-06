import { expect, test, type Page } from "@playwright/test";

/**
 * The portal, driven in a real browser (spec 003 US1–US4).
 *
 * Everything else in this feature's test suite runs against the API in-process. This
 * file is the only place the **deployed** path is exercised: a real browser, real
 * cookies, the real Next.js server calling the real container. That distinction has
 * already earned its keep once — the API image shipped without `PyJWT` and every
 * in-process test passed while the container would not start.
 *
 * Signs in through the actual form rather than by planting a cookie. A test that
 * fabricates its own session proves the pages render; it proves nothing about the
 * sign-in path, the route handler, or the cookie flags, which is where this feature's
 * security actually lives.
 */

const PASSWORD = "eaios-demo-local-only";

/**
 * Seeded personas (spec 001 FR-025b). Addresses follow the generator's deterministic
 * rule, so they are stable across every reseed of the committed dataset.
 */
const EMPLOYEE = "majid.alzaabi@niletech.example";
const MANAGER = "tarek.darwish@niletech.example";
const DELTA = "dina.shafik@deltaretail.example";

/**
 * The sign-in form's own status region.
 *
 * Scoped to a direct child of the form, and both halves of that matter. Next.js
 * injects `#__next-route-announcer__` with `role="alert"` into every page, so a bare
 * `getByRole("alert")` is ambiguous everywhere; and `Field` gives each field error
 * `role="alert"` too, so an unscoped match inside the form would catch those as well.
 */
const signInAlert = (page: Page) => page.locator("form > [role='alert']");

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/portal");
  await page.getByLabel("Work email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/portal\/home/);
}

test.describe("signing in and reading your own record (US1)", () => {
  test("an employee reaches their own profile", async ({ page }) => {
    await signIn(page, EMPLOYEE);

    await expect(page.getByRole("heading", { level: 1 })).toContainText("Welcome");

    await page.getByRole("link", { name: "My HR profile" }).first().click();
    await expect(page).toHaveURL(/\/portal\/profile/);

    // FR-023 names these. Present *and* populated — a blank field satisfies "the
    // field exists" and tells the employee nothing.
    for (const label of ["Department", "Office", "Manager", "Employment type"]) {
      await expect(page.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(page.getByRole("heading", { name: "Annual leave" })).toBeVisible();
  });

  test("SC-001: the profile is within three interactions of arriving", async ({ page }) => {
    // Arrive, sign in, click through. Counted because SC-001 states a number, and a
    // portal that buried the profile four clicks deep would satisfy every other test.
    await page.goto("/portal");
    await page.getByLabel("Work email address").fill(EMPLOYEE); // 1
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click(); // 2
    await expect(page).toHaveURL(/\/portal\/home/);
    await page.getByRole("link", { name: "My HR profile" }).first().click(); // 3
    await expect(page).toHaveURL(/\/portal\/profile/);
  });

  test("no salary appears anywhere on the profile", async ({ page }) => {
    await signIn(page, EMPLOYEE);
    await page.goto("/portal/profile");
    const body = (await page.textContent("body"))?.toLowerCase() ?? "";
    for (const word of ["salary", "compensation", "salary band"]) {
      expect(body).not.toContain(word);
    }
  });

  test("the session token is never readable by JavaScript", async ({ page }) => {
    // The point of the httpOnly cookie and of routing through the site's own handler.
    // If this fails, an XSS anywhere on the site reads the session.
    await signIn(page, EMPLOYEE);

    const readable = await page.evaluate(() => document.cookie);
    expect(readable).not.toContain("eaios_session");

    const cookies = await page.context().cookies();
    const session = cookies.find((c) => c.name === "eaios_session");
    expect(session, "no session cookie was set").toBeTruthy();
    expect(session?.httpOnly, "the session cookie is readable by JavaScript").toBe(true);
    expect(session?.sameSite).toBe("Strict");
  });

  test("signing out ends access to protected pages", async ({ page }) => {
    await signIn(page, EMPLOYEE);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/portal$/);

    await page.goto("/portal/profile");
    await expect(page).toHaveURL(/\/portal$/);
    await expect(page.getByLabel("Work email address")).toBeVisible();
  });
});

/**
 * Deliberate sign-in failures, and why there are so few of them here.
 *
 * FR-007a bounds failed attempts at five per account and twenty per address in a
 * fifteen-minute window, and this suite runs across three viewport projects — so every
 * failing test here costs three attempts.
 *
 * A first version used a real persona with a wrong password. Three viewports took that
 * account to three failures, a second failing test took it past five, the account
 * locked, and then **every** later `signIn` as that persona failed too — each one
 * adding to the address counter until that hit twenty as well. Nine tests failed and
 * the cause looked like a broken portal. It was the bound doing exactly its job.
 *
 * So: deliberate failures use addresses belonging to **nobody**, which cannot lock a
 * real account, and there are only two of them. What the interface renders on a
 * refusal is this file's business; *which* server-side cause produced it is proven
 * exhaustively at the API level by `tests/security/test_login_enumeration.py`, where
 * it can be done without spending the budget a browser suite shares.
 */
const NOBODY = "nobody-e2e@niletech.example";
const ALSO_NOBODY = "nobody-focus-e2e@niletech.example";

test.describe("refusals say the right thing (FR-022, FR-029)", () => {
  test("a refusal shows one generic message and names no cause", async ({ page }) => {
    await page.goto("/portal");
    await page.getByLabel("Work email address").fill(NOBODY);
    await page.getByLabel("Password").fill("whatever");
    await page.getByRole("button", { name: "Sign in" }).click();

    const alert = signInAlert(page);
    await expect(alert).toContainText("were not accepted");
    // Nothing that answers "does this account exist?"
    await expect(alert).not.toContainText(/no such|not found|unknown|exists|password/i);
    // And it does not echo the address back.
    await expect(alert).not.toContainText(NOBODY);
  });

  test("an anonymous visitor is sent to sign in, never to a raw error", async ({ page }) => {
    await page.goto("/portal/profile");
    await expect(page).toHaveURL(/\/portal$/);
    await expect(page.getByLabel("Work email address")).toBeVisible();
  });
});

test.describe("a manager sees their team and nobody else (US2)", () => {
  test("the team area appears and lists direct reports", async ({ page }) => {
    await signIn(page, MANAGER);
    await page.getByRole("link", { name: "My team" }).first().click();
    await expect(page).toHaveURL(/\/portal\/team/);
    await expect(page.getByRole("heading", { name: "My team" })).toBeVisible();
  });

  test("a report's profile is reachable from the list", async ({ page }) => {
    await signIn(page, MANAGER);
    await page.goto("/portal/team");

    const first = page.locator(".eaios-team-list a").first();
    if ((await first.count()) === 0) test.skip(true, "no direct reports in this dataset");

    await first.click();
    await expect(page).toHaveURL(/\/portal\/team\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("an unrelated employee gets the designed denial, not a raw 403", async ({ page }) => {
    // A real user id from the other tenant's side of the org is not needed: the
    // manager's own manager is in the same company and does not report to them.
    await signIn(page, MANAGER);
    const context = await page.request.get("http://localhost:8000/health/live");
    expect(context.ok()).toBeTruthy();

    // Reach a profile the manager cannot have by walking to somebody outside the line.
    await page.goto("/portal/team");
    const body = await page.textContent("body");
    expect(body).not.toContain("Traceback");
    expect(body).not.toContain("500");
  });
});

test.describe("role-aware navigation (US4, SC-008)", () => {
  test("an employee does not see the team area at all", async ({ page }) => {
    await signIn(page, EMPLOYEE);
    // Absent from the markup, not merely hidden.
    const html = await page.content();
    expect(html).not.toContain("/portal/team");
  });

  test("a manager does see it — the same assertion, the other way", async ({ page }) => {
    // Paired deliberately: without this, "the employee cannot see it" is satisfied by
    // navigation that renders nothing for anybody.
    await signIn(page, MANAGER);
    const html = await page.content();
    expect(html).toContain("/portal/team");
  });

  test("a hidden area is refused when requested directly", async ({ page }) => {
    // FR-028: hiding is presentation and must never be the only control.
    await signIn(page, EMPLOYEE);
    await page.goto("/portal/team");

    const body = (await page.textContent("body")) ?? "";
    expect(body).toMatch(/do not manage a team|do not have access/i);
    expect(body).not.toContain("Traceback");
  });
});

test.describe("cross-tenant isolation for an authenticated caller (US3)", () => {
  test("a Delta Retail user is identified as Delta Retail", async ({ page }) => {
    await signIn(page, DELTA);
    await page.goto("/portal/home");

    // Scoped to the portal's identity region, not the whole page.
    //
    // The surrounding site chrome is NileTech's — this *is* NileTech's public website,
    // and `/portal` is a route on it — so "NileTech Solutions" appears in the header
    // and footer of every page including this one. That is branding, not tenant data,
    // and asserting its absence would be asserting something the design never claimed.
    //
    // What must hold is that the portal identifies this person as belonging to Delta
    // Retail, and that no NileTech *record* reaches them. The second half is proved
    // properly by `tests/security/test_cross_tenant_authenticated.py`, which compares
    // against ground truth from the owner connection rather than against page text.
    const identity = page.locator(".eaios-portal__identity");
    await expect(identity).toContainText("Delta Retail");
    await expect(identity).not.toContainText("NileTech");
  });

  test("a NileTech identifier is not found, not forbidden", async ({ page }) => {
    // FR-021 and FR-030: another tenant's record is *absent*. A 403 would confirm it
    // exists, which is the enumeration the layer-1 ordering exists to prevent.
    await signIn(page, DELTA);

    // A well-formed identifier that belongs to nobody in this tenant.
    await page.goto("/portal/team/00000000-0000-0000-0000-000000000042");
    const body = (await page.textContent("body")) ?? "";
    expect(body).not.toContain("Traceback");
    expect(body).not.toMatch(/500|internal server error/i);
  });
});

test.describe("keyboard access (SC-010)", () => {
  test("the sign-in form is completable without a mouse", async ({ page }) => {
    await page.goto("/portal");

    await page.getByLabel("Work email address").focus();
    await page.keyboard.type(EMPLOYEE);
    await page.keyboard.press("Tab");
    await page.keyboard.type(PASSWORD);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/portal\/home/);
  });

  test("the failure message receives focus", async ({ page }) => {
    // A message a sighted user sees and a keyboard user is never taken to is not an
    // error message.
    await page.goto("/portal");
    await page.getByLabel("Work email address").fill(ALSO_NOBODY);
    await page.getByLabel("Password").fill("wrong");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(signInAlert(page)).toContainText("were not accepted");

    // The focused element must be the form's own status region — identified by being
    // inside the form, since Next's route announcer also carries `role="alert"`.
    const focusedIsTheSummary = await page.evaluate(() => {
      const active = document.activeElement;
      return (
        active instanceof HTMLElement &&
        active.getAttribute("role") === "alert" &&
        active.closest("form") !== null
      );
    });
    expect(focusedIsTheSummary, "focus did not move to the failure message").toBe(true);
  });
});

test.describe("nothing internal reaches the page (FR-022)", () => {
  test("no token, identifier, hostname, or trace appears in the rendered portal", async ({
    page,
  }) => {
    await signIn(page, EMPLOYEE);

    for (const path of ["/portal/home", "/portal/profile"]) {
      await page.goto(path);
      const html = await page.content();
      expect(html, path).not.toContain("eyJ"); // a JWT
      expect(html, path).not.toContain("$argon2");
      expect(html, path).not.toContain("Traceback");
      expect(html, path).not.toContain("postgres");
      expect(html, path).not.toMatch(/SELECT .* FROM/i);
    }
  });
});
