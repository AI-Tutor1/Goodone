# syntax=docker/dockerfile:1.7
# Tuitional Finance — frontend (React + Vite, served by nginx).

FROM node:20-bookworm-slim AS builder

ENV CI=true
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend ./
RUN npm run build


# ---------------------------------------------------------------------------

FROM nginx:1.27-alpine AS runtime

# nginx config: serve the SPA + proxy /api/* → backend service.
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ || exit 1
