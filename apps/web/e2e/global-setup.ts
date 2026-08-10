/**
 * Resolve the seeded personas once, before the browser suite runs.
 *
 * Node has no database client here and adding one would put a second copy of "who is
 * seeded" in the repository. The lookup instead goes through the project's own Python
 * layer — the same `eaios_core` owner connection `tests/security/auth_helpers.py` uses
 * — so there is exactly one answer to that question and both suites read it.
 *
 * Fails the run outright if the personas cannot be resolved. A browser suite that
 * silently proceeded without them would report 70 login failures instead of one clear
 * "the environment is not seeded".
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { delimiter, dirname } from "node:path";

import { DELTA_KEY, EMPLOYEE_KEY, MANAGER_KEY, PERSONA_FILE, ROOT } from "./personas";

/**
 * Reads `users.persona_key` — the identifier spec 001 FR-025b pins — and prints the
 * mapping as JSON. The owner engine deliberately, exactly as `auth_helpers.load_person`
 * documents: this is establishing ground truth about who exists, and the application
 * role would prove only that a filtered view is filtered.
 */
const QUERY = `
import json
from sqlalchemy import text
from eaios_core.db import create_owner_engine

with create_owner_engine().connect() as conn:
    rows = conn.execute(text(
        "SELECT persona_key, email, full_name FROM users WHERE persona_key IS NOT NULL"
    )).mappings().all()
print(json.dumps({r["persona_key"]: {"email": r["email"], "fullName": r["full_name"]} for r in rows}))
`;

export default function globalSetup(): void {
  let stdout: string;
  try {
    stdout = execFileSync("uv", ["run", "python", "-c", QUERY], {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        ...process.env,
        // `path.delimiter` — `;` on Windows, `:` on the Linux runner. Hard-coding
        // either one breaks the other platform, and an inherited PYTHONPATH is kept
        // rather than replaced so a caller's own entries survive.
        PYTHONPATH: ["packages/core/src", "apps/api/src", process.env.PYTHONPATH]
          .filter(Boolean)
          .join(delimiter),
        // Compose publishes the stores on the host; the browser suite runs on the host
        // too, so the container hostnames in `.env` do not resolve. `tests/conftest.py`
        // makes the same substitution for the same reason.
        POSTGRES_HOST: process.env.POSTGRES_HOST ?? "localhost",
        PYTHONIOENCODING: "utf-8",
      },
    });
  } catch (cause) {
    throw new Error(
      "Could not resolve seeded personas. The browser suite signs in as real seeded " +
        "users, so it needs a running, seeded stack: `make up && make seed && make credentials`.",
      { cause },
    );
  }

  const resolved = JSON.parse(stdout) as Record<string, { email: string; fullName: string }>;

  const missing = [EMPLOYEE_KEY, MANAGER_KEY, DELTA_KEY].filter((key) => !resolved[key]);
  if (missing.length > 0) {
    throw new Error(
      `The seeded dataset is missing personas the browser suite drives: ${missing.join(", ")}. ` +
        `FR-025b guarantees the fixed set in every profile, so this environment was seeded ` +
        `with something other than this generator.`,
    );
  }

  mkdirSync(dirname(PERSONA_FILE), { recursive: true });
  writeFileSync(PERSONA_FILE, JSON.stringify(resolved, null, 2), "utf8");
}
