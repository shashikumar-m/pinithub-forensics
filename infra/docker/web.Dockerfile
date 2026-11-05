# ---- Frontend (Vite) Dockerfile ----
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
COPY packages/shared/package.json ./packages/shared/package.json
COPY apps/web/package.json ./apps/web/package.json

RUN npm install --workspaces --include-workspace-root

COPY packages/shared ./packages/shared
COPY apps/web ./apps/web

RUN npm --workspace @pinithub/shared run build
RUN npm --workspace @pinithub/web run build

# ---- Runtime (static preview) ----
FROM node:20-alpine AS runner

WORKDIR /app

RUN npm install -g vite

COPY --from=builder /app/apps/web/dist ./dist
COPY --from=builder /app/apps/web/package.json ./package.json

EXPOSE 5173

CMD ["vite", "preview", "--host", "0.0.0.0", "--port", "5173"]
