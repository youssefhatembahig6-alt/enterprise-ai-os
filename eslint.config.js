// @ts-check
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
      "**/*.min.js",
      // The Python virtualenv ships JavaScript (urllib3's emscripten worker,
      // pywin32's test scriptlets). Without this, `pnpm lint` reports 19 errors
      // from third-party files that are not project source at all.
      ".venv/**",
      "**/site-packages/**",
      "**/__pycache__/**",
      ".git/**",
      // Generated from the FastAPI OpenAPI schema — edits belong upstream (T064).
      "packages/contracts/src/generated/**",
      // Next.js build output and its generated ambient declarations. Without
      // this, `pnpm lint` reports thousands of errors from compiled chunks —
      // the same shape as the .venv problem above, and just as misleading.
      "**/.next/**",
      "apps/web/next-env.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Build scripts run under Node, not in a browser or a bundler. Without this the
    // shared config flags `process` and `console` as undefined globals in files
    // whose whole job is to be a Node CLI.
    files: ["**/scripts/**/*.mjs", "*.config.js", "*.config.mjs"],
    languageOptions: {
      globals: { process: "readonly", console: "readonly", URL: "readonly" },
    },
  },
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
);
