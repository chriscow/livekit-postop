#!/bin/bash

# PostOp AI Discharge Agent Startup Script
# This script starts the discharge agent locally for demos

set -e  # Exit on any error

echo "🎯 Starting PostOp AI Discharge Agent (Local Mode)"
echo "=================================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo "Please make sure you're in the project root directory"
    exit 1
fi

# Load environment variables
echo "📋 Loading environment variables..."
set -a
source .env
set +a

# Validate required environment variables
if [ -z "$LIVEKIT_AGENT_NAME" ]; then
    echo "❌ Error: LIVEKIT_AGENT_NAME not set in .env"
    exit 1
fi

if [ -z "$LIVEKIT_API_KEY" ]; then
    echo "❌ Error: LIVEKIT_API_KEY not set in .env"
    exit 1
fi

if [ -z "$LIVEKIT_URL" ]; then
    echo "❌ Error: LIVEKIT_URL not set in .env"
    exit 1
fi

echo "✅ Environment loaded successfully"
echo "   Agent Name: $LIVEKIT_AGENT_NAME"
echo "   LiveKit URL: $LIVEKIT_URL"

# Check if Redis is running
echo "🔍 Checking Redis connection..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Error: Redis is not running"
    echo "Please start Redis with: redis-server"
    echo "Or use Docker: docker run -d --name redis -p 6379:6379 redis:alpine"
    exit 1
fi
echo "✅ Redis is running"

# Stop any existing Docker agents to avoid conflicts
echo "🛑 Stopping Docker agents to avoid conflicts..."
docker-compose stop postop-agent > /dev/null 2>&1 || true

# Start RQ workers for outbound calling
echo "🔧 Ensuring RQ workers are running for outbound calls..."
docker-compose up -d postop-worker postop-scheduler > /dev/null 2>&1 || true
sleep 2

# Kill any existing local agents
echo "🧹 Cleaning up existing local agents..."
pkill -f "python main.py discharge dev" > /dev/null 2>&1 || true
sleep 2

echo ""
echo "🚀 Starting PostOp AI agent in development mode..."
echo "📞 Inbound calls: +1 (844) 970-1900 → Discharge collection"
echo "📱 Outbound calls: Automatic courtesy callbacks after discharge"
echo ""
echo "🔧 Demo commands available:"
echo "   ./show_pending_calls.sh           # Show scheduled outbound calls"
echo "   ./trigger_outbound_call.sh <id>   # Execute call immediately"
echo "   ./trigger_outbound_call.sh create +phone 'Name'  # Create test call"
echo "   ./reset_demo.sh                   # Clear demo data, restore medical knowledge"
echo ""
echo "Press Ctrl+C to stop the agent"
echo "=================================================="

# Start the agent
exec uv run python main.py discharge dev