import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end coverage for the public site.
 *
 * The three projects are the widths FR-032 names — 360px mobile, 768px tablet,
 * 1280px desktop. They are declared here rather than set per test so a new spec
 * file is covered at all three by default; a width that has to be opted into is
 * a width that gets forgotten.
 *
 * Tests run against an already-running stack (`make up`). Playwright does not
 * start the server itself: the site needs the API and a seeded database, and a
 * webServer block that started only Next would produce a site with no content
 * and failures that look like missing data rather than a missing stack.
 */
const baseURL = process.env.SITE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],

  /**
   * Capped, and the cap is the point.
   *
   * Every test here drives one API container and one database. Playwright defaults to
   * roughly one worker per core and multiplies that across three viewport projects, so
   * on a developer machine the suite was opening enough concurrent requests to push
   * server-rendered pages past their own 10-second API timeout. The symptom was a
   * different test failing on a different project on each full run — `metadata`, then
   * `content-journeys` — which reads as a broken page and is actually queueing.
   *
   * Four keeps the suite parallel enough to finish in a couple of minutes and stops it
   * competing with itself. Raising it does not make the stack faster; it makes the
   * failures less reproducible, which is the opposite of what this project is for.
   */
  workers: process.env.CI ? 2 : 4,

  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "mobile-360",
      use: { ...devices["Desktop Chrome"], viewport: { width: 360, height: 740 } },
    },
    {
      name: "tablet-768",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "desktop-1280",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
  ],
});
