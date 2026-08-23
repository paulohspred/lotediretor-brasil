FROM node:22-alpine AS build
WORKDIR /workspace
COPY package.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/admin-web ./apps/admin-web
RUN npm install --workspaces --include-workspace-root
RUN npm run build -w @lotediretor/admin-web
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /workspace/apps/admin-web/.next/standalone ./
COPY --from=build /workspace/apps/admin-web/.next/static ./apps/admin-web/.next/static
COPY --from=build /workspace/apps/admin-web/public ./apps/admin-web/public
EXPOSE 3000
CMD ["node","apps/admin-web/server.js"]
