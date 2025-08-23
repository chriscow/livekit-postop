# PostOp AI Dockerfile for NextJS frontend and LiveKit agent
# syntax=docker/dockerfile:1

# Global ARG declaration
ARG PYTHON_VERSION=3.11.6

# Stage 1: Build NextJS frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Install pnpm and dependencies
RUN npm install -g pnpm
RUN pnpm install --frozen-lockfile

# Copy source code and build
COPY . .
RUN pnpm build

# Stage 2: Python runtime with NextJS static files
FROM python:${PYTHON_VERSION}-slim

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Install Node.js for serving NextJS
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm && \
    rm -rf /var/lib/apt/lists/*

# Create a non-privileged user that the app will run under.
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

USER appuser

RUN mkdir -p /home/appuser/.cache
RUN chown -R appuser /home/appuser/.cache

WORKDIR /home/appuser

# Copy Python requirements and install dependencies
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --user --no-cache-dir -r requirements.txt

# Copy agent code
COPY agent/ ./agent/

# Copy NextJS build and dependencies from previous stage
COPY --from=frontend-builder /app/.next ./.next
COPY --from=frontend-builder /app/public ./public
COPY --from=frontend-builder /app/package.json ./package.json
COPY --from=frontend-builder /app/pnpm-lock.yaml ./pnpm-lock.yaml
COPY --from=frontend-builder /app/next.config.ts ./next.config.ts
COPY --from=frontend-builder /app/node_modules ./node_modules

# Install production dependencies
RUN cd /home/appuser && pnpm install --prod --frozen-lockfile

# Set Python path
ENV PYTHONPATH=/home/appuser

# Expose ports for both services
EXPOSE 3000 8081

# Copy startup script (as root, then change ownership)
USER root
COPY start.sh /home/appuser/start.sh
RUN chmod +x /home/appuser/start.sh && chown appuser:appuser /home/appuser/start.sh
USER appuser

# Default command - run both services
CMD ["/home/appuser/start.sh"]