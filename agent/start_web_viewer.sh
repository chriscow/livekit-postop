#!/bin/bash

# PostOp AI Conversation Web Viewer Startup Script

echo "🌐 Starting PostOp AI Health Check Server with Conversation Viewer..."

# Check if Redis is running
if ! redis-cli ping >/dev/null 2>&1; then
    echo "❌ Redis is not running. Please start Redis first:"
    echo "   redis-server"
    exit 1
fi

# The conversation viewer is now integrated into the health check server
# This runs the same server that Fly.io uses, but accessible locally

echo "✅ Starting health check server with conversation viewer on port 8081..."
echo "🌐 Open http://localhost:8081 to view conversations"
echo "🔍 Health check available at http://localhost:8081/health"
echo ""

# Load environment variables from .env file
if [ -f .env ]; then
    echo "✅ Loading environment variables from .env..."
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Check if virtual environment is available
if command -v uv >/dev/null 2>&1; then
    echo "✅ Using uv to run server..."
    PYTHONPATH=. uv run python healthcheck_server.py 8081
else
    echo "✅ Running server directly..."
    cd "$(dirname "$0")"
    PYTHONPATH=. python healthcheck_server.py 8081
fi