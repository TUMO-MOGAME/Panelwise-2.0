# Panelwise web. Versions pinned per PLAN.md § Technical Context.
FROM node:24.21.0-trixie-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /srv/web

# Dependencies first, so a code change doesn't reinstall them.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# The browser's Supabase pair is baked into the bundle here; empty builds a signed-out app.
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
RUN pnpm run build

FROM node:24.21.0-trixie-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /srv/web
COPY --from=build --chown=node:node /srv/web/.next/standalone ./
COPY --from=build --chown=node:node /srv/web/.next/static ./.next/static
USER node

EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r => process.exit(r.status === 200 ? 0 : 1), () => process.exit(1))"
CMD ["node", "server.js"]
