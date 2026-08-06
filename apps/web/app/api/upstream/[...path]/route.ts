import { NextResponse } from "next/server";

import { apiBaseServer } from "../../../../lib/config";

/**
 * Read-only proxy for the anonymous operational endpoints (spec 002 FR-003).
 *
 * **Why this exists.** The status page is a client component and fetched
 * `http://localhost:8000/health/live` straight from the browser. That is a *simple*
 * request, so no preflight is sent — but the response is still unreadable to
 * JavaScript unless the API returns `Access-Control-Allow-Origin`, and it returns none.
 * Verified against the running stack: `GET /health/live` with an `Origin` header
 * answers 200 with no CORS header at all, so `fetch(...).json()` rejects.
 *
 * The same root cause as the contact form, in a second place, and equally invisible:
 * `apps/web/tests/StatusPage.test.tsx` stubs `fetch`, so it proves the page renders
 * what it is handed and never that it can obtain anything.
 *
 * **Deliberately an allowlist, not a general proxy.** An open path-forwarding route on
 * the site's own origin would be a way for a browser to reach *any* API address with
 * the server's network position — including the authenticated ones — which is exactly
 * the boundary feature 003 spent its length establishing. Three anonymous read-only
 * paths, named individually, and everything else is 404.
 */

/** The only paths this route will forward. Anonymous and read-only, all three. */
const ALLOWED = new Set(["health/live", "health/ready", "dataset/manifest"]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  const target = path.join("/");

  if (!ALLOWED.has(target)) {
    // Not "forbidden" — as far as this route is concerned the address does not exist,
    // and saying otherwise would confirm which internal paths are real.
    return NextResponse.json(
      { title: "Not found", status: 404, detail: "No such record." },
      { status: 404 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseServer()}/${target}`, { cache: "no-store" });
  } catch {
    return NextResponse.json(
      { title: "Unavailable", status: 502, detail: "We could not reach our systems." },
      { status: 502 },
    );
  }

  // Status preserved. A 503 from `/health/ready` carries the per-dependency detail
  // that makes a partial outage visible (FR-003), and a proxy that normalised it to
  // 200 or 500 would throw away the only thing the status page is for.
  const text = await upstream.text();
  return new NextResponse(text || null, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
