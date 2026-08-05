# syntax=docker/dockerfile:1

# The public NileTech website (spec 002).
#
# A production build rather than `next dev`, unlike the Vite shell this replaces.
# Dev mode compiles a route on its first request, which would put a multi-second
# delay in front of the first visitor to every page — exactly what SC-014 budgets
# against. Content is read from the API at request time, so nothing is gained by
# rebuilding on change in a demo stack.

FROM node:20-bookworm-slim AS base
ENV LANG=C.UTF-8 \
    TZ=UTC \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

# --------------------------------------------------------------- dependencies
FROM base AS deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN pnpm install --frozen-lockfile

# ---------------------------------------------------------------------- build
FROM base AS build
# Every workspace package's own node_modules, not just the app's. pnpm installs
# each package's dependencies beside it, so copying only the root and `apps/web`
# leaves `packages/ui` unable to resolve its own `@types/react` and the type check
# fails on a module that resolves perfectly on the host.
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/ui/node_modules ./packages/ui/node_modules
COPY --from=deps /app/packages/contracts/node_modules ./packages/contracts/node_modules
COPY tsconfig.base.json package.json pnpm-workspace.yaml ./
COPY packages/ui packages/ui
COPY packages/contracts packages/contracts
COPY apps/web apps/web
RUN pnpm --filter @eaios/web build

# --------------------------------------------------------------------- runner
FROM base AS runner
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output carries its own minimal node_modules, so the runner needs
# neither pnpm nor the rest of the workspace.
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./apps/web/.next/static

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
