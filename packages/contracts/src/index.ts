/**
 * Shared API contract types.
 *
 * `src/generated/api.ts` is produced by `make contracts` from the live FastAPI
 * OpenAPI schema — never edit it by hand; change the Pydantic models instead and
 * regenerate.
 *
 * The aliases below give consumers stable names. Without them every call site
 * would spell out `components["schemas"]["ReadinessResponse"]`, and an API rename
 * would ripple through the frontend instead of stopping here.
 */

import type { components, paths } from "./generated/api";

export type { components, paths };

export type Schemas = components["schemas"];

export type LivenessResponse = Schemas["LivenessResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];
export type DependencyStatus = Schemas["DependencyStatusModel"];
export type DatasetManifest = Schemas["DatasetManifestResponse"];

export type DependencyName = DependencyStatus["name"];
export type DependencyState = DependencyStatus["status"];

/**
 * The public website surface (spec 002).
 *
 * Generated from the same OpenAPI schema the API serves, so the field allowlist in
 * `contracts/public-fields.md` reaches the frontend as types. A field the backend
 * stops returning becomes a compile error here rather than an undefined at runtime.
 */
export type PublicCompany = Schemas["CompanyOut"];
export type PublicOffice = Schemas["OfficeOut"];
export type PublicService = Schemas["ServiceOut"];
export type PublicProduct = Schemas["ProductOut"];
export type PublicLeader = Schemas["LeadershipOut"];
export type PublicNewsItem = Schemas["NewsOut"];
export type PublicNewsDetail = Schemas["NewsDetailOut"];
export type PublicNewsPage = Schemas["NewsPage"];
export type PublicVacancy = Schemas["VacancyOut"];
export type PublicVacancyDetail = Schemas["VacancyDetailOut"];
export type ContactSubmissionInput = Schemas["ContactIn"];
export type ContactAccepted = Schemas["ContactAccepted"];

/**
 * The public error envelopes, generated rather than transcribed.
 *
 * These did not exist here until the API declared them. FastAPI published its
 * default `HTTPValidationError` for every public route while actually returning
 * `ValidationProblem`, so `apps/web/lib/api.ts` hand-wrote the real shape from a
 * comment pointing at `contracts/public-api.yaml`. A type copied by hand from a
 * document is the drift this package exists to prevent.
 */
export type ValidationProblem = Schemas["ValidationProblem"];
export type FieldError = Schemas["FieldError"];
export type Problem = Schemas["Problem"];

/**
 * The authenticated surface (spec 003).
 *
 * `Problem` above is shared with the public site deliberately: 401, 403, and 404 on
 * this surface use the same envelope, so the portal has one shape to handle rather
 * than a second error vocabulary that would drift from the first.
 *
 * `LoginAccepted` carries the token, and the portal's route handler is the only thing
 * that ever touches that field — it moves the value into an httpOnly cookie and hands
 * the browser nothing. The type is exported so that handler can be typed, not so
 * components can reach for it.
 */
export type LoginRequest = Schemas["LoginRequest"];
export type LoginAccepted = Schemas["LoginAccepted"];
export type SessionState = Schemas["SessionState"];

export type CurrentUser = Schemas["CurrentUser"];
export type AccessContextView = Schemas["AccessContextView"];

export type HrProfile = Schemas["HrProfile"];
export type LeaveBalanceView = Schemas["LeaveBalanceView"];
export type DirectReport = Schemas["DirectReport"];
export type Compensation = Schemas["Compensation"];

/**
 * The permission codes the portal's navigation branches on (FR-028).
 *
 * Role-aware navigation is built from these and never from role names — FR-014 makes
 * that a rule, and an interface branching on a role name would break the moment roles
 * are recomposed.
 *
 * This list is *not* generated: OpenAPI describes `permissions` as `string[]`, so the
 * schema cannot tell us which codes exist. It is transcribed from the seeded catalog
 * in `scripts/seed/.../organization.py`, and `apps/web/tests/PortalNav.test.tsx`
 * checks it against what the API actually returns — because a hand-kept list is
 * exactly the kind of thing this package exists to be suspicious of.
 */
export const PORTAL_PERMISSIONS = [
  "hr:read_self",
  "hr:read_team",
  "hr:read_all",
  "audit:read",
] as const;

export type PortalPermission = (typeof PORTAL_PERMISSIONS)[number];

/**
 * Every backing service the readiness probe reports on (spec FR-003).
 *
 * Five, not four: US1 acceptance scenario 3 names the background worker alongside
 * the stores, and a stack whose worker has died must not report `ready`.
 *
 * The exhaustiveness assertion below is the part that earns its keep: without it a
 * dependency added to the API would leave this list quietly short, and a `readonly
 * DependencyName[]` annotation would not notice — it rejects a *wrong* name, never
 * a *missing* one.
 */
export const DEPENDENCY_NAMES = ["postgres", "redis", "qdrant", "minio", "worker"] as const;

type UncoveredDependency = Exclude<DependencyName, (typeof DEPENDENCY_NAMES)[number]>;

/** Fails to compile if the API declares a dependency this list omits. */
export const DEPENDENCY_NAMES_ARE_EXHAUSTIVE: UncoveredDependency extends never
  ? true
  : never = true;

export const CONTRACTS_PACKAGE_VERSION = "0.1.0";
