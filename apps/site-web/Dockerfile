FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/site-web ./apps/site-web
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
RUN npm run build -w @lotediretor/site-web

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /workspace/apps/site-web/.next/standalone ./
COPY --from=build --chown=node:node /workspace/apps/site-web/.next/static ./apps/site-web/.next/static
COPY --from=build --chown=node:node /workspace/apps/site-web/public ./apps/site-web/public
USER node
EXPOSE 3000
CMD ["node","apps/site-web/server.js"]
