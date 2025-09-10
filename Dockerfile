# PostOp AI Dockerfile for NextJS frontend only
# syntax=docker/dockerfile:1

# Stage 1: Build NextJS frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Install pnpm and dependencies
RUN npm install -g pnpm
RUN pnpm install --frozen-lockfile

# Copy source code and build (exclude agent directory)
COPY . .
RUN pnpm build

# Stage 2: Production runtime with NextJS
FROM node:20-alpine AS runtime

# Install pnpm globally
RUN npm install -g pnpm

# Create a non-privileged user that the app will run under
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

USER appuser

WORKDIR /home/appuser

# Copy NextJS build and dependencies from previous stage
COPY --from=frontend-builder --chown=appuser:appuser /app/.next ./.next
COPY --from=frontend-builder --chown=appuser:appuser /app/public ./public
COPY --from=frontend-builder --chown=appuser:appuser /app/package.json ./package.json
COPY --from=frontend-builder --chown=appuser:appuser /app/pnpm-lock.yaml ./pnpm-lock.yaml
COPY --from=frontend-builder --chown=appuser:appuser /app/next.config.ts ./next.config.ts
COPY --from=frontend-builder --chown=appuser:appuser /app/node_modules ./node_modules

# Expose port for NextJS
EXPOSE 3000

# Start NextJS server
CMD ["pnpm", "start"]