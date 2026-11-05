# ---- Node.js API Dockerfile ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy root package manifest for workspace resolution
COPY package.json package-lock.json* ./
COPY packages/shared/package.json ./packages/shared/package.json
COPY apps/api/package.json ./apps/api/package.json

# Install dependencies
RUN npm install --workspaces --include-workspace-root

# Copy source
COPY packages/shared ./packages/shared
COPY apps/api ./apps/api

# Build shared package first
RUN npm --workspace @pinithub/shared run build

# Build API
RUN npm --workspace @pinithub/api run build

# ---- Runtime ----
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/apps/api/node_modules ./apps/api/node_modules
COPY --from=builder /app/packages/shared/node_modules ./packages/shared/node_modules
COPY --from=builder /app/packages/shared/dist ./packages/shared/dist
COPY --from=builder /app/apps/api/dist ./apps/api/dist
COPY --from=builder /app/apps/api/prisma ./apps/api/prisma

EXPOSE 4000

CMD ["node", "apps/api/dist/index.js"]
