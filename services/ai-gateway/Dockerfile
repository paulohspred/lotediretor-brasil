FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json tsconfig.base.json ./
COPY services/ai-gateway ./services/ai-gateway
RUN npm install --workspaces --include-workspace-root
RUN npm run build -w @lotediretor/ai-gateway
FROM node:22-alpine
WORKDIR /workspace
COPY --from=build /workspace/node_modules ./node_modules
COPY --from=build /workspace/services/ai-gateway/dist ./services/ai-gateway/dist
CMD ["node","services/ai-gateway/dist/main.js"]
