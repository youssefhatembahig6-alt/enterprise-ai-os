"use client";

/**
 * Environment status shell.
 *
 * This is deliberately not a product UI — confirmed scope decision D1 defers the
 * public site and the employee portal to a later feature. It exists so the Compose
 * stack is complete (spec FR-002) and so a developer can see per-dependency health
 * without reading JSON.
 *
 * It still implements the loading, empty, and error states the constitution
 * requires of any frontend surface, because those states are the whole point of a
 * status page.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchManifest,
  fetchReadiness,
  type DatasetManifest,
  type ReadinessResponse,
} from "../../lib/health";

type LoadState = "loading" | "loaded" | "error";

export function StatusPage() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [manifest, setManifest] = useState<DatasetManifest | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const [ready, seeded] = await Promise.all([fetchReadiness(), fetchManifest()]);
      setReadiness(ready);
      setManifest(seeded);
      setState("loaded");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setState("error");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 10_000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "3rem auto" }}>
      <h1>Enterprise AI OS — Environment Status</h1>

      {state === "loading" && !readiness && <p role="status">Checking services…</p>}

      {state === "error" && (
        <section role="alert" style={{ padding: "1rem", border: "1px solid var(--danger)", borderRadius: 6 }}>
          <h2>Cannot reach the API</h2>
          <p>{error}</p>
          <p>
            The stack may still be starting. Try <code>make up</code>, then reload.
          </p>
          <button onClick={() => void load()}>Retry</button>
        </section>
      )}

      {readiness && (
        <section aria-labelledby="deps">
          <h2 id="deps">Dependencies</h2>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={cell}>Service</th>
                <th style={cell}>Status</th>
                <th style={cell}>Latency</th>
              </tr>
            </thead>
            <tbody>
              {readiness.dependencies.map((dependency) => (
                <tr key={dependency.name}>
                  <td style={cell}>{dependency.name}</td>
                  <td style={cell}>
                    <span aria-label={dependency.status}>
                      {dependency.status === "up" ? "✅" : "❌"} {dependency.status}
                    </span>
                    {dependency.detail ? ` (${dependency.detail})` : ""}
                  </td>
                  <td style={cell}>{dependency.latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section aria-labelledby="dataset">
        <h2 id="dataset">Dataset</h2>
        {manifest === null && state === "loaded" && (
          <p>
            No dataset yet. Run <code>make seed</code> to populate the two synthetic companies.
          </p>
        )}
        {manifest && (
          <dl>
            <dt>Seed</dt>
            <dd>{manifest.root_seed}</dd>
            <dt>Reference date</dt>
            <dd>{manifest.reference_date}</dd>
            <dt>Fingerprint</dt>
            <dd>
              <code>{manifest.root_fingerprint.slice(0, 16)}…</code>
            </dd>
            <dt>Complete</dt>
            <dd>{manifest.is_complete ? "yes" : "no — seed was interrupted"}</dd>
          </dl>
        )}
      </section>
    </main>
  );
}

const cell: React.CSSProperties = {
  textAlign: "left",
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid var(--border)",
};
