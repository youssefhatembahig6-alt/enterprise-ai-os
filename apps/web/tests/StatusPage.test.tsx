/**
 * Status page behaviour (spec FR-003, Mandatory Surfaces).
 *
 * `pnpm test` previously exited 1 with "No test files found" — the script was
 * declared but had never passed, so the CI web job could not go green.
 *
 * The states covered here are the ones the constitution requires of any frontend
 * surface: loading, error, empty, and populated. The degraded case matters most:
 * a 503 from /health/ready is a *meaningful* response carrying per-dependency
 * detail, and throwing it away would hide exactly the information FR-003 exists
 * to surface.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEPENDENCY_NAMES } from "@eaios/contracts";

import { StatusPage } from "../app/status/StatusPage";

const READY = {
  status: "ready",
  dependencies: [
    { name: "postgres", status: "up", latency_ms: 3, detail: null },
    { name: "redis", status: "up", latency_ms: 1, detail: null },
    { name: "qdrant", status: "up", latency_ms: 7, detail: null },
    { name: "minio", status: "up", latency_ms: 4, detail: null },
    { name: "worker", status: "up", latency_ms: 12, detail: null },
  ],
};

const DEGRADED = {
  status: "degraded",
  dependencies: [
    { name: "postgres", status: "up", latency_ms: 3, detail: null },
    { name: "redis", status: "up", latency_ms: 1, detail: null },
    { name: "qdrant", status: "down", latency_ms: 2000, detail: "ConnectionRefusedError" },
    { name: "minio", status: "up", latency_ms: 4, detail: null },
    { name: "worker", status: "up", latency_ms: 12, detail: null },
  ],
};

/**
 * The case that was invisible before the worker became a reported dependency:
 * every store answers, the broker answers, and nothing is draining the queue.
 */
const WORKER_DOWN = {
  status: "degraded",
  dependencies: [
    { name: "postgres", status: "up", latency_ms: 3, detail: null },
    { name: "redis", status: "up", latency_ms: 1, detail: null },
    { name: "qdrant", status: "up", latency_ms: 7, detail: null },
    { name: "minio", status: "up", latency_ms: 4, detail: null },
    { name: "worker", status: "down", latency_ms: 2000, detail: "no worker answered the ping" },
  ],
};

const MANIFEST = {
  root_seed: "20260630",
  reference_date: "2026-06-30",
  generator_version: "0.1.5",
  profile: "smoke",
  entity_counts: {},
  root_fingerprint: "4b0d85e20aa86d591500ebd1df46243a680ad662cf5b987b4e90752198e8e460",
  completed_at: "2026-08-01T09:18:14Z",
  is_complete: true,
};

function mockFetch(handlers: Record<string, { status: number; body: unknown }>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(handlers).find((path) => url.includes(path));
    if (!key) throw new Error(`unmocked request: ${url}`);
    const { status, body } = handlers[key]!;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    } as Response;
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("loading state", () => {
  it("shows a status message before data arrives", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<StatusPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("ready state", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/health/ready": { status: 200, body: READY },
        "/dataset/manifest": { status: 200, body: MANIFEST },
      }),
    );
  });

  it("lists every dependency", async () => {
    render(<StatusPage />);
    // Driven by the contract's own list rather than a copy of it, so a dependency
    // added to the API cannot be missing from the page and still pass here.
    for (const name of DEPENDENCY_NAMES) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
  });

  it("covers the background worker, not only the stores", async () => {
    render(<StatusPage />);
    expect(await screen.findByText("worker")).toBeInTheDocument();
  });

  it("shows each dependency's latency", async () => {
    render(<StatusPage />);
    expect(await screen.findByText("3 ms")).toBeInTheDocument();
  });

  it("renders the dataset fingerprint when seeded", async () => {
    render(<StatusPage />);
    expect(await screen.findByText(/4b0d85e20aa86d59/)).toBeInTheDocument();
  });
});

describe("degraded state", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        // 503 is expected, not an error — it carries the detail FR-003 requires.
        "/health/ready": { status: 503, body: DEGRADED },
        "/dataset/manifest": { status: 200, body: MANIFEST },
      }),
    );
  });

  it("names the failing dependency", async () => {
    render(<StatusPage />);
    const row = await screen.findByLabelText("down");
    expect(row).toBeInTheDocument();
  });

  it("still reports the healthy dependencies as up", async () => {
    render(<StatusPage />);
    await waitFor(() => {
      expect(screen.getAllByLabelText("up")).toHaveLength(DEPENDENCY_NAMES.length - 1);
    });
  });

  it("does not treat a 503 as a page-level error", async () => {
    render(<StatusPage />);
    expect(await screen.findByText("qdrant")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("worker outage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/health/ready": { status: 503, body: WORKER_DOWN },
        "/dataset/manifest": { status: 200, body: MANIFEST },
      }),
    );
  });

  it("reports the worker as down while every store is up", async () => {
    render(<StatusPage />);
    await waitFor(() => {
      expect(screen.getAllByLabelText("up")).toHaveLength(4);
    });
    expect(screen.getByLabelText("down")).toBeInTheDocument();
  });

  it("explains why the worker failed", async () => {
    render(<StatusPage />);
    expect(await screen.findByText(/no worker answered the ping/)).toBeInTheDocument();
  });
});

describe("empty state", () => {
  it("invites seeding when no dataset exists", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/health/ready": { status: 200, body: READY },
        // 404 means "never seeded" — a normal state, not a failure.
        "/dataset/manifest": { status: 404, body: {} },
      }),
    );
    render(<StatusPage />);
    expect(await screen.findByText(/make seed/)).toBeInTheDocument();
  });
});

describe("error state", () => {
  it("shows an alert when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Failed to fetch");
      }),
    );
    render(<StatusPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/make up/)).toBeInTheDocument();
  });

  it("offers a retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Failed to fetch");
      }),
    );
    render(<StatusPage />);
    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
