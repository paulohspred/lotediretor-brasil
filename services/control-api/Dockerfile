FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json tsconfig.base.json ./
COPY packages ./packages
COPY services/control-api ./services/control-api
COPY db ./db
RUN npm install --workspaces --include-workspace-root
RUN npm run build -w @lotediretor/control-api
FROM node:22-alpine
WORKDIR /workspace
ENV NODE_ENV=production
COPY --from=build /workspace/node_modules ./node_modules
COPY --from=build /workspace/services/control-api/dist ./services/control-api/dist
COPY --from=build /workspace/db ./db
CMD ["node","services/control-api/dist/main.js"]
