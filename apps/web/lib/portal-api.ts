/**
 * Typed client for the authenticated API (spec 003).
 *
 * Types come from `@eaios/contracts`, generated from the API's own OpenAPI schema, so
 * a field the backend stops returning is a compile error here rather than an
 * `undefined` at runtime.
 *
 * **Four outcomes, not two.** `lib/api.ts` needed two — it worked or it did not.
 * Here the difference between them is the feature:
 *
 * * `Unauthenticated` — no session. Show the way in.
 * * `SessionExpired` — there *was* a session and it ended. Say so; FR-005's edge case
 *   requires the interface to distinguish this from never having signed in, and a
 *   generic failure after a thirty-minute pause reads as broken rather than as secure.
 * * `Forbidden` — signed in, refused. The designed access-denied state (FR-029).
 * * `NotFound` — no such record *for this caller*, which is also what a resource in
 *   another tenant looks like. That the two are indistinguishable is the requirement.
 *
 * Collapsing any pair of these is the defect FR-029 exists to prevent, so they are
 * separate classes rather than a status code the caller has to branch on correctly.
 */

import type {
  AccessContextView,
  Compensation,
  CurrentUser,
  DirectReport,
  HrProfile,
  SessionState,
} from "@eaios/contracts";

import { apiBaseServer } from "./config";
import { authHeaders, sessionToken } from "./session";

export type { AccessContextView, Compensation, CurrentUser, DirectReport, HrProfile, SessionState };

/** No credential was presented, or it was never valid. */
export class UnauthenticatedError extends Error {
  constructor() {
    super("Not signed in");
    this.name = "UnauthenticatedError";
  }
}

/**
 * A session existed in this browser and the server no longer accepts it.
 *
 * Distinguished from `UnauthenticatedError` by the *presence of a cookie*, not by
 * anything the API says — the API refuses both identically and deliberately, because
 * a response that told them apart would tell an attacker which sessions are real.
 * The browser knows something the server must not reveal: that it was holding one.
 */
export class SessionExpiredError extends Error {
  constructor() {
    super("Session ended");
    this.name = "SessionExpiredError";
  }
}

/** Signed in, and refused by authorization. */
export class ForbiddenError extends Error {
  constructor() {
    super("Not permitted");
    this.name = "ForbiddenError";
  }
}

/** No such record for this caller — including one that belongs to another tenant. */
export class PortalNotFoundError extends Error {
  constructor() {
    super("Not found");
    this.name = "PortalNotFoundError";
  }
}

/** Anything else. Carries no server detail; FR-022 forbids exposing it. */
export class PortalApiError extends Error {
  constructor(readonly status: number) {
    super(`Request failed with status ${status}`);
    this.name = "PortalApiError";
  }
}

/** Matches `lib/api.ts`. An unbounded loading state is one SC-014 forbids. */
const TIMEOUT_MS = 10_000;

async function get<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  if (!headers) throw new UnauthenticatedError();

  const response = await fetch(`${apiBaseServer()}${path}`, {
    headers,
    // Never cached. A response scoped to one person's permissions sitting in a shared
    // cache is precisely the leak Principle III is about, and `no-store` is the only
    // safe default until the permission-fingerprinted cache exists.
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });

  if (response.status === 401) {
    // The cookie was present — `authHeaders` would have returned null otherwise — so
    // this is a session that ended rather than one that never began.
    throw (await sessionToken()) ? new SessionExpiredError() : new UnauthenticatedError();
  }
  if (response.status === 403) throw new ForbiddenError();
  if (response.status === 404) throw new PortalNotFoundError();
  if (!response.ok) throw new PortalApiError(response.status);

  return (await response.json()) as T;
}

export const getCurrentUser = () => get<CurrentUser>("/me");
export const getAccessContext = () => get<AccessContextView>("/me/access-context");
export const getOwnProfile = () => get<HrProfile>("/me/hr-profile");
export const getDirectReports = () => get<DirectReport[]>("/me/direct-reports");
export const getSessionState = () => get<SessionState>("/auth/session");

export const getProfile = (userId: string) =>
  get<HrProfile>(`/hr/profiles/${encodeURIComponent(userId)}`);

export const getCompensation = (userId: string) =>
  get<Compensation>(`/hr/profiles/${encodeURIComponent(userId)}/compensation`);

/**
 * Whether this caller holds a permission code.
 *
 * Codes, never role names (FR-014). A helper rather than an inline `includes` so every
 * navigation decision reads the same way and a search for `hasPermission` finds all of
 * them — which is what makes the role-aware navigation audit tractable.
 */
export function hasPermission(user: CurrentUser, code: string): boolean {
  return user.permissions.includes(code);
}
