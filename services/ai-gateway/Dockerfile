FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json tsconfig.base.json ./
COPY services/ai-gateway ./services/ai-gateway
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
RUN npm run build -w @lotediretor/ai-gateway

FROM node:22-alpine
WORKDIR /workspace
ENV NODE_ENV=production
COPY --from=build --chown=node:node /workspace/node_modules ./node_modules
COPY --from=build --chown=node:node /workspace/services/ai-gateway/dist ./services/ai-gateway/dist
USER node
CMD ["node","services/ai-gateway/dist/main.js"]
