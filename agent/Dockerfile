# This is an example Dockerfile that builds a minimal container for running LK Agents
# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11.6
FROM python:${PYTHON_VERSION}-slim

# Build-time arguments for environment variables needed during build
ARG OPENAI_API_KEY
ARG DEEPGRAM_API_KEY
ARG ELEVEN_API_KEY
ARG CARTESIA_API_KEY

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


# Install gcc and other build dependencies.
RUN apt-get update && \
    apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

USER appuser

RUN mkdir -p /home/appuser/.cache
RUN chown -R appuser /home/appuser/.cache

WORKDIR /home/appuser

COPY requirements.txt .
RUN python -m pip install --user --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables for the download-files command
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
ENV ELEVEN_API_KEY=${ELEVEN_API_KEY}
ENV CARTESIA_API_KEY=${CARTESIA_API_KEY}

# ensure that any dependent models are downloaded at build-time
RUN python -m discharge.agents download-files

# expose healthcheck port
EXPOSE 8081

# Run the application.
CMD ["python","-m","discharge.agents","start"]
