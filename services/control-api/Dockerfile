FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json tsconfig.base.json ./
COPY packages ./packages
COPY services/control-api ./services/control-api
COPY db ./db
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
RUN npm run build -w @lotediretor/control-api

FROM node:22-alpine
WORKDIR /workspace
ENV NODE_ENV=production
COPY --from=build --chown=node:node /workspace/node_modules ./node_modules
COPY --from=build --chown=node:node /workspace/services/control-api/dist ./services/control-api/dist
COPY --from=build --chown=node:node /workspace/db ./db
USER node
CMD ["node","services/control-api/dist/main.js"]
