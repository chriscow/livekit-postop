# PostOp AI Dockerfile for scheduling system and agents
# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11.6
FROM python:${PYTHON_VERSION}-slim

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install minimal system dependencies
RUN apt-get update && \
    apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

USER appuser

RUN mkdir -p /home/appuser/.cache
RUN chown -R appuser /home/appuser/.cache

WORKDIR /home/appuser

# Copy requirements and install dependencies
COPY requirements.txt .
RUN python -m pip install --user --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Medical knowledge is stored in Redis (no local data directory needed)

# Set Python path
ENV PYTHONPATH=/home/appuser

# Expose healthcheck port
EXPOSE 8081

# Default command - run discharge workflow in production mode with embedded health endpoint
CMD ["python", "main.py", "discharge", "dev"]