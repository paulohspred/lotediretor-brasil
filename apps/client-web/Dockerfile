FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/client-web ./apps/client-web
RUN npm install --workspaces --include-workspace-root
RUN npm run build -w @lotediretor/client-web
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /workspace/apps/client-web/.next/standalone ./
COPY --from=build /workspace/apps/client-web/.next/static ./apps/client-web/.next/static
COPY --from=build /workspace/apps/client-web/public ./apps/client-web/public
EXPOSE 3000
CMD ["node","apps/client-web/server.js"]
