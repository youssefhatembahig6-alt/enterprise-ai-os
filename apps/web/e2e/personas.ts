/**
 * Seeded personas, resolved from the running dataset rather than written down.
 *
 * The addresses used to be literals — `majid.alzaabi@niletech.example` and friends.
 * Those are the people the *full* profile generates. CI seeds `smoke`, where the same
 * persona lands on a different generated person, so every browser sign-in was refused
 * with a 401 and 70 tests failed on a correct application.
 *
 * `persona_key` is the stable identifier the seed guarantees (spec 001 FR-025b), and
 * it is what the Python suites already key on — `tests/security/auth_helpers.py` looks
 * personas up the same way, through the owner connection, for the same reason: this is
 * ground truth about who exists, and it must not be a second copy of the generator's
 * naming rule. `global-setup.ts` performs the lookup once and writes the result here.
 *
 * Hard-coding a *different* set of addresses for smoke would have fixed the symptom and
 * kept the defect: two profiles, two lists, and nothing to notice when either moves.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** `apps/web/e2e/`. Absolute, so the path does not depend on where Playwright was run. */
const HERE = dirname(fileURLToPath(import.meta.url));

/** Repo root, from `apps/web/e2e/`. */
export const ROOT = resolve(HERE, "../../..");

/** Where `global-setup.ts` leaves the resolved set. Gitignored (`test-results/`). */
export const PERSONA_FILE = resolve(HERE, "../test-results/personas.json");

/**
 * The three identities the browser suite drives, named by the same persona keys the
 * Python security suite uses so both are talking about the same people.
 */
export const EMPLOYEE_KEY = "employee.engineering";
export const MANAGER_KEY = "manager.engineering";
export const DELTA_KEY = "employee.delta";

/** Local-only demo credential (spec 003 FR-002a); `.env.example` carries the same value. */
export const PASSWORD = "eaios-demo-local-only";

export type Persona = { email: string; fullName: string };

let cache: Record<string, Persona> | undefined;

function load(): Record<string, Persona> {
  if (cache) return cache;
  try {
    cache = JSON.parse(readFileSync(PERSONA_FILE, "utf8")) as Record<string, Persona>;
  } catch (cause) {
    throw new Error(
      `Could not read ${PERSONA_FILE}. Playwright's global setup resolves personas from ` +
        `the seeded database before the suite runs; if it did not, the stack is probably ` +
        `not up or not seeded. Run \`make up && make seed && make credentials\`.`,
      { cause },
    );
  }
  return cache;
}

/**
 * The sign-in address for a persona.
 *
 * Throws rather than returning a placeholder: an unresolved persona must fail as a
 * missing precondition, not as a login that mysteriously does not work.
 */
export function persona(key: string): Persona {
  const found = load()[key];
  if (!found) {
    throw new Error(
      `persona ${key} is not present in the seeded dataset (found: ` +
        `${Object.keys(load()).sort().join(", ") || "none"}). The seed guarantees the ` +
        `fixed persona set in every profile (FR-025b), so this means the environment is ` +
        `seeded with something else.`,
    );
  }
  return found;
}

export const employee = (): string => persona(EMPLOYEE_KEY).email;
export const manager = (): string => persona(MANAGER_KEY).email;
export const delta = (): string => persona(DELTA_KEY).email;
