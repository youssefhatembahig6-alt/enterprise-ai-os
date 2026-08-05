/**
 * Typed client for the public API (spec 002).
 *
 * Types come from `@eaios/contracts`, generated from the API's own OpenAPI schema,
 * so the declared field allowlist reaches the frontend as types rather than as an
 * assumption.
 *
 * Every read goes through `getJson`, which is the single place a failed request
 * becomes an error state. Scattering that decision across pages is how one page
 * ends up rendering an empty list on a 500 — indistinguishable, to a visitor, from
 * a company that genuinely has no services.
 */

import type {
  ContactAccepted,
  ContactSubmissionInput,
  FieldError,
  PublicCompany,
  PublicLeader,
  PublicNewsDetail,
  PublicNewsPage,
  PublicOffice,
  PublicProduct,
  PublicService,
  PublicVacancy,
  Problem,
  PublicVacancyDetail,
  ValidationProblem,
} from "@eaios/contracts";

import { apiBase, apiBaseServer } from "./config";

export type {
  ContactAccepted,
  ContactSubmissionInput,
  FieldError,
  PublicCompany,
  PublicLeader,
  PublicNewsDetail,
  PublicNewsPage,
  PublicOffice,
  PublicProduct,
  PublicService,
  PublicVacancy,
  Problem,
  PublicVacancyDetail,
  ValidationProblem,
};

/** Distinguishes "the record does not exist" from "the request failed". */
export class NotFoundError extends Error {
  constructor(path: string) {
    super(`Not found: ${path}`);
    this.name = "NotFoundError";
  }
}

/** Any other failure. Carries no server detail — FR-027 forbids exposing it. */
export class ApiError extends Error {
  constructor(
    path: string,
    readonly status: number,
  ) {
    super(`Request to ${path} failed with status ${status}`);
    this.name = "ApiError";
  }
}

/**
 * FR-027a: a client-fetched region becomes an error state after 10 seconds. The
 * same bound is applied to server-side reads so a wedged API cannot hold a page
 * render open indefinitely — SC-014 forbids an unbounded loading state, and a
 * request with no timeout is exactly that.
 */
const TIMEOUT_MS = 10_000;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseServer()}${path}`, {
    // Content changes only on reseed, but caching it here would make a reseed
    // invisible until the process restarted (research R7).
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });

  if (response.status === 404) throw new NotFoundError(path);
  if (!response.ok) throw new ApiError(path, response.status);
  return (await response.json()) as T;
}

export const getCompany = () => getJson<PublicCompany>("/public/company");
export const getOffices = () => getJson<PublicOffice[]>("/public/offices");
export const getServices = () => getJson<PublicService[]>("/public/services");
export const getProducts = () => getJson<PublicProduct[]>("/public/products");
export const getLeadership = () => getJson<PublicLeader[]>("/public/leadership");

export const getNews = (limit = 20, offset = 0) =>
  getJson<PublicNewsPage>(`/public/news?limit=${limit}&offset=${offset}`);

export const getNewsItem = (slug: string) =>
  getJson<PublicNewsDetail>(`/public/news/${encodeURIComponent(slug)}`);

export function getVacancies(filters: { office?: string; department?: string } = {}) {
  const query = new URLSearchParams();
  if (filters.office) query.set("office", filters.office);
  if (filters.department) query.set("department", filters.department);
  const suffix = query.toString() ? `?${query}` : "";
  return getJson<PublicVacancy[]>(`/public/vacancies${suffix}`);
}

export const getVacancy = (slug: string) =>
  getJson<PublicVacancyDetail>(`/public/vacancies/${encodeURIComponent(slug)}`);

/**
 * The outcomes a submission can have, as three named cases rather than two plus an
 * exception.
 *
 * The third one exists because a 429 used to fall through to `ApiError`, and the
 * form's catch-all then told the visitor "we could not reach our systems just now"
 * — every clause of which is false when the server understood the message perfectly
 * and refused it on purpose (FR-024d). A refusal the interface cannot distinguish
 * from an outage is one it will describe wrongly.
 */
export type ContactOutcome =
  | { ok: true }
  | { ok: false; kind: "invalid"; errors: FieldError[] }
  | { ok: false; kind: "bounded"; message: string };

/**
 * The one write path. Returns the server's field-addressed validation errors
 * unchanged so the form can attach each to its control (FR-021), and the server's
 * own wording when the per-address bound is reached (FR-024d) — the API composes
 * that sentence, so a second copy written here would be one more thing to drift.
 */
export async function submitContact(input: ContactSubmissionInput): Promise<ContactOutcome> {
  const response = await fetch(`${apiBase()}/public/contact`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });

  if (response.ok) return { ok: true };

  if (response.status === 422) {
    // `ValidationProblem` comes from the API's own schema now. It used to be
    // written out here by hand, because the published schema advertised FastAPI's
    // `HTTPValidationError` while the server sent this — so the generated types had
    // no name for the shape the form actually receives (FR-021).
    const body = (await response.json()) as Partial<ValidationProblem>;
    return {
      ok: false,
      kind: "invalid",
      errors: body.errors ?? [
        { field: "form", message: "Please check the details above and try again." },
      ],
    };
  }

  if (response.status === 429) {
    // FR-024d. The body is a `Problem`; its `detail` is the sentence written for a
    // visitor. The fallback covers a refusal that arrives without one — better a
    // vague true statement than a specific false one.
    const body = (await response.json()) as Partial<Problem>;
    return {
      ok: false,
      kind: "bounded",
      message:
        body.detail ??
        "We have received several messages from you recently. Please try again later.",
    };
  }

  throw new ApiError("/public/contact", response.status);
}
