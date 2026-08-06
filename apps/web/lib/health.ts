/**
 * Typed client for the health endpoints.
 *
 * Types come from `@eaios/contracts`, generated from the live FastAPI OpenAPI
 * schema. They were previously hand-declared here, which meant the contract and
 * the client could drift apart silently — a renamed field would type-check on both
 * sides and fail only at runtime.
 */

import type {
  DatasetManifest,
  DependencyName,
  DependencyStatus,
  LivenessResponse,
  ReadinessResponse,
} from "@eaios/contracts";

export type {
  DatasetManifest,
  DependencyName,
  DependencyStatus,
  LivenessResponse,
  ReadinessResponse,
};

/**
 * The site's own origin, not the API's.
 *
 * This was `apiBaseBrowser()` — the API's host-facing address — and the status page is
 * a client component, so every one of these fetches was cross-origin from the browser.
 * They are simple GETs, so no preflight is sent and the request reaches the API; the
 * *response* is then unreadable to JavaScript, because the API sends no
 * `Access-Control-Allow-Origin`. Confirmed against the running stack.
 *
 * `apps/web/tests/StatusPage.test.tsx` stubs `fetch`, so it proved the page renders
 * what it is given and never that it could obtain anything. Same defect as the contact
 * form, same fix: go through the site's own origin.
 */
const API_BASE = "/api/upstream";

export async function fetchLiveness(): Promise<LivenessResponse> {
  const response = await fetch(`${API_BASE}/health/live`);
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status} from /health/live`);
  }
  return (await response.json()) as LivenessResponse;
}

export async function fetchReadiness(): Promise<ReadinessResponse> {
  const response = await fetch(`${API_BASE}/health/ready`);
  // 503 is an expected, meaningful response: it carries the per-dependency detail
  // that makes a partial outage visible (FR-003), so it must not be thrown away.
  if (response.status !== 200 && response.status !== 503) {
    throw new Error(`Unexpected status ${response.status} from /health/ready`);
  }
  return (await response.json()) as ReadinessResponse;
}

export async function fetchManifest(): Promise<DatasetManifest | null> {
  const response = await fetch(`${API_BASE}/dataset/manifest`);
  if (response.status === 404) {
    return null; // never seeded — a normal state, not an error
  }
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status} from /dataset/manifest`);
  }
  return (await response.json()) as DatasetManifest;
}
