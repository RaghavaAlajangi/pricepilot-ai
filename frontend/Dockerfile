# Build context is the frontend/ directory.

# ---- stage 1: install dependencies -----------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- stage 2: build ----------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked into the client bundle at build time (public, not a secret).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ---- stage 3: runtime --------------------------------------------------------
FROM node:20-alpine

WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER node
EXPOSE 3000
# ${PORT} is set by Cloud Run; defaults to 3000 for docker compose
CMD ["sh", "-c", "PORT=${PORT:-3000} node server.js"]
