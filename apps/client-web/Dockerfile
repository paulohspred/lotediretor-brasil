FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/client-web ./apps/client-web
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
RUN npm run build -w @lotediretor/client-web

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /workspace/apps/client-web/.next/standalone ./
COPY --from=build --chown=node:node /workspace/apps/client-web/.next/static ./apps/client-web/.next/static
COPY --from=build --chown=node:node /workspace/apps/client-web/public ./apps/client-web/public
USER node
EXPOSE 3000
CMD ["node","apps/client-web/server.js"]
