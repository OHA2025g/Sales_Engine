# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /repo
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/config/package.json ./packages/config/package.json
COPY packages/sdk/package.json ./packages/sdk/package.json
COPY packages/types/package.json ./packages/types/package.json
COPY packages/ui/package.json ./packages/ui/package.json
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store \
    && pnpm config set package-import-method copy \
    && pnpm install --frozen-lockfile

FROM deps AS build
COPY apps/web ./apps/web
COPY packages ./packages
WORKDIR /repo/apps/web
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_DISABLE_ESLINT=1 \
    SKIP_NEXT_TYPECHECK=1 \
    NEXT_BUILD_CPUS=4 \
    NODE_OPTIONS=--max-old-space-size=3072
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN --mount=type=cache,id=next-cache,target=/repo/apps/web/.next/cache \
    pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
RUN addgroup -S agrayian && adduser -S -G agrayian agrayian
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=agrayian:agrayian /repo/apps/web/.next/standalone ./
COPY --from=build --chown=agrayian:agrayian /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=agrayian:agrayian /repo/apps/web/public ./apps/web/public
USER agrayian
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD node -e "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
