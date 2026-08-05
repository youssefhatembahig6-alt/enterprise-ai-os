/**
 * Fail if the committed API types no longer match the served schema.
 *
 * `src/generated/api.ts` is committed deliberately — `.gitignore` records the
 * decision — and produced by a manual `pnpm generate`. Nothing kept the two in step:
 * `pnpm typecheck` runs against the committed file, so a stale one typechecks
 * perfectly while the frontend builds against types for an API that no longer
 * exists. The drift is not hypothetical; changing the public error models required
 * remembering to regenerate by hand, and forgetting would have been invisible.
 *
 * This is the same shape as `make docs-check`, which fails when the committed docs
 * stop matching the dataset. Regenerate, compare, report the difference.
 *
 * Line endings are normalised before comparing. The repository checks out with
 * `core.autocrlf` unset in CI but not necessarily on a developer's Windows machine,
 * and a CRLF difference is not a contract change — CI already carries a step
 * warning that "a CRLF here would silently change every generated document's bytes".
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const committed = join(packageRoot, "src", "generated", "api.ts");
const schemaUrl = process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json";

const normalise = (text) => text.replace(/\r\n/g, "\n").trimEnd();

/** First differing line, so the failure names something specific. */
function firstDifference(a, b) {
  const left = a.split("\n");
  const right = b.split("\n");
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    if (left[index] !== right[index]) {
      return {
        line: index + 1,
        committed: left[index] ?? "<end of file>",
        served: right[index] ?? "<end of file>",
      };
    }
  }
  return null;
}

const scratch = mkdtempSync(join(tmpdir(), "eaios-contracts-"));
const regenerated = join(scratch, "api.ts");

try {
  execFileSync(
    process.execPath,
    [join(packageRoot, "..", "..", "node_modules", "openapi-typescript", "bin", "cli.js"), schemaUrl, "-o", regenerated],
    { stdio: "inherit" },
  );

  const before = normalise(readFileSync(committed, "utf-8"));
  const after = normalise(readFileSync(regenerated, "utf-8"));

  // Guard against passing on an empty comparison: an unreachable API or a failed
  // generation must not read as "no drift". This is the failure mode the whole
  // check exists to prevent, so it is checked first.
  if (after.length < 500) {
    console.error(`Regenerated schema is only ${after.length} bytes — the API was probably not reachable at ${schemaUrl}.`);
    process.exit(2);
  }

  if (before === after) {
    console.log(`Contract types match the schema served at ${schemaUrl}.`);
    process.exit(0);
  }

  const difference = firstDifference(before, after);
  console.error("The committed API types no longer match the served schema.\n");
  if (difference) {
    console.error(`  first difference at line ${difference.line}`);
    console.error(`    committed: ${difference.committed}`);
    console.error(`    served:    ${difference.served}\n`);
  }
  console.error("Run `make contracts` (or `pnpm --filter @eaios/contracts generate`) and commit the result.");
  process.exit(1);
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
