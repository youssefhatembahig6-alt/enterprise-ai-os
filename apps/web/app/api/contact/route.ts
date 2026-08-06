import { NextResponse } from "next/server";

import { apiBaseServer } from "../../../lib/config";

/**
 * The contact form's submission path, on the site's own origin (spec 002 FR-023).
 *
 * **This exists because the form did not work in a real browser.** `ContactForm` is a
 * client component; it posted `application/json` from `localhost:3000` directly to the
 * API on `localhost:8000`. That is a cross-origin request with a non-simple content
 * type, so the browser sends a CORS preflight first — and the API registers no CORS
 * middleware at all. The preflight had nothing to answer it.
 *
 * Nothing caught it. The server-side tests post to the endpoint directly, where no
 * origin check applies. Every browser-level test stubbed the request with Playwright's
 * `page.route`, so the real network path was never exercised — the tests asserted that
 * the form handles a response, never that it can obtain one. Feature 003 found this
 * while designing the portal (research F1) and routed the portal around it; this closes
 * it for the form that has been shipping broken.
 *
 * **Same-origin rather than a CORS policy**, matching `app/portal/api/*`. One
 * architecture for browser-to-API traffic instead of two, no credentialed cross-origin
 * configuration to get wrong in each deployment, and no preflight at all.
 *
 * The API's response is passed through **unchanged** — status and body. The 422 field
 * errors and the 429 bound message are both written by the API for a person to read,
 * and a proxy that reworded either would be a second place for that wording to live.
 */
export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { title: "Invalid request", status: 400, detail: "Expected a JSON body." },
      { status: 400 },
    );
  }

  // The visitor's own address, forwarded so the API's per-address bound still counts
  // *visitors*. Without it every submission arrives from this container and five
  // enquiries an hour from anybody would exhaust the allowance for everybody — a
  // denial-of-service surface created by the proxy, not by the attacker.
  //
  // The API believes this header only from hosts on its `TRUSTED_PROXY_HOSTS` list, so
  // a value forged by a visitor is ignored.
  const forwarded =
    request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip") ?? "";

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseServer()}/public/contact`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(forwarded ? { "x-forwarded-for": forwarded } : {}),
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    // The API is unreachable from the server. Reported as a gateway failure so the
    // form's catch-all says "we could not reach our systems" — which is true — rather
    // than mistaking an outage for a rejection.
    return NextResponse.json(
      { title: "Unavailable", status: 502, detail: "We could not reach our systems." },
      { status: 502 },
    );
  }

  const text = await upstream.text();
  return new NextResponse(text || null, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
