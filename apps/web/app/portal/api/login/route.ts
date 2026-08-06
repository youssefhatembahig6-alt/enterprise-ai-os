import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import { apiBaseServer } from "../../../../lib/config";
import { CSRF_COOKIE, SESSION_COOKIE } from "../../../../lib/session";

/**
 * Sign-in, on the site's own origin (spec 003 research R3).
 *
 * The browser posts here, not to the API. Three things follow from that, and each is
 * the reason for it:
 *
 * 1. **The token never reaches browser JavaScript.** The API returns it in the body;
 *    this handler moves it into an `httpOnly` cookie and answers `{ ok: true }`. An
 *    XSS on this site cannot read the session, because the value never enters a
 *    variable the page can see.
 * 2. **No CORS.** Same origin, so no preflight and no credentialed cross-origin
 *    configuration to get wrong. That matters more than it sounds: the public site's
 *    contact form posts cross-origin to an API that registers *no* CORS middleware,
 *    and every browser test of it stubs the request — so that path has never actually
 *    been exercised (research F1). Building sign-in on top of it would be building on
 *    an untested assumption.
 * 3. **One place to get the cookie flags right**, rather than a rule every future
 *    caller has to remember.
 *
 * The refusal is passed through **unchanged**: same status, same body. The API is
 * deliberate about every sign-in failure looking identical (FR-022), and a helpful
 * proxy that added "no such account" here would undo that from the outside.
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

  const upstream = await fetch(`${apiBaseServer()}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!upstream.ok) {
    // Verbatim. Status and body both — the API decides what a refusal says.
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  const accepted = (await upstream.json()) as { access_token: string; expires_at: string };

  // `{ ok: true }` and nothing else. Returning the user object here would be
  // convenient and would also mean the browser held a copy of the identity the server
  // is about to re-derive on every request anyway — one more thing to go stale.
  const response = NextResponse.json({ ok: true });

  const maxAge = Math.max(
    0,
    Math.floor((new Date(accepted.expires_at).getTime() - Date.now()) / 1000),
  );

  response.cookies.set(SESSION_COOKIE, accepted.access_token, {
    httpOnly: true,
    // Chrome and Firefox treat `http://localhost` as a trustworthy origin, so this
    // holds in local development as well as behind TLS.
    secure: true,
    sameSite: "strict",
    path: "/",
    // Matches the session's absolute cap. The cookie expiring is a convenience for the
    // browser; the server enforces both bounds regardless (FR-005), and an interface
    // that hid an expired session without the server refusing it would not satisfy it.
    maxAge,
  });

  // Readable by JavaScript — that is what makes double-submit work. An attacker on
  // another origin can cause the cookie to be sent but cannot read it to build the
  // matching header.
  response.cookies.set(CSRF_COOKIE, randomUUID(), {
    httpOnly: false,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge,
  });

  return response;
}
