FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json tsconfig.base.json ./
COPY services/event-dispatcher ./services/event-dispatcher
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
RUN npm run build -w @lotediretor/event-dispatcher

FROM node:22-alpine
WORKDIR /workspace
ENV NODE_ENV=production
COPY --from=build /workspace/node_modules ./node_modules
COPY --from=build /workspace/services/event-dispatcher/dist ./services/event-dispatcher/dist
CMD ["node","services/event-dispatcher/dist/main.js"]
