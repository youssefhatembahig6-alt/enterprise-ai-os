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

import { apiBaseBrowser } from "./config";

export type {
  DatasetManifest,
  DependencyName,
  DependencyStatus,
  LivenessResponse,
  ReadinessResponse,
};

// The status page is a client component, so this resolves to the host-facing
// address. `NEXT_PUBLIC_` values are inlined at build time, which is why a
// module-level constant is correct here rather than a per-call read.
const API_BASE = apiBaseBrowser();

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
